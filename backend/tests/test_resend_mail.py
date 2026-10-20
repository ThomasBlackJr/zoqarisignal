import json
from unittest.mock import Mock

import httpx
import pytest

from app.config import Settings
from app.services.account_mail import build_mail, build_message, MailUnavailable, LocalMail, SMTPMail, DisabledMail
from app.services.graph_mail import GraphMail
from app.services.resend_mail import ResendMail
from tools import send_test_email


def settings(**changes):
    return Settings(
        _env_file=None, **{"mail_delivery": "resend", "resend_api_key": "re_synthetic_unit_test_only", **changes}
    )


def test_settings_provider_selection_secrets_and_production(tmp_path):
    value = settings()
    assert value.resend_from == "AccountManagement@zoqari.com"
    assert isinstance(build_mail(value), ResendMail)
    assert "re_synthetic_unit_test_only" not in repr(value)
    assert "re_synthetic_unit_test_only" not in value.model_dump_json()
    assert isinstance(
        build_mail(
            settings(
                environment="production",
                database_url="postgresql://fixture@localhost/test",
                frontend_origin="https://signal.example.test",
                cookie_secure=True,
            )
        ),
        ResendMail,
    )
    assert isinstance(build_mail(settings(mail_delivery="disabled")), DisabledMail)
    assert isinstance(build_mail(settings(mail_delivery="local", mail_outbox_dir=tmp_path)), LocalMail)
    assert isinstance(
        build_mail(settings(mail_delivery="smtp", smtp_host="smtp.example.test", mail_from="sender@example.test")),
        SMTPMail,
    )
    assert isinstance(
        build_mail(
            settings(
                mail_delivery="graph",
                m365_tenant_id="11111111-1111-1111-1111-111111111111",
                m365_client_id="22222222-2222-2222-2222-222222222222",
                m365_client_secret="synthetic-graph-secret",
            )
        ),
        GraphMail,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"resend_api_key": ""},
        {"resend_api_key": "wrong-format"},
        {"resend_api_key": "re_"},
        {"resend_api_key": "re_private\nkey"},
        {"resend_api_key": "re_private\x00key"},
        {"resend_from": "not-an-email"},
        {"resend_from": "Sender <sender@example.test>"},
        {"resend_from": "sender@example.test\r\nBcc: private@example.test"},
    ],
)
def test_invalid_configuration_is_safe(changes):
    with pytest.raises(ValueError) as error:
        settings(**changes)
    assert "re_private" not in str(error.value)


def test_dotenv_loads_requested_mode_and_sender(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "MAIL_DELIVERY=resend\nRESEND_API_KEY=re_synthetic_unit_test_only\nRESEND_FROM=AccountManagement@zoqari.com\n"
    )
    value = Settings(_env_file=env)
    assert value.mail_delivery == "resend" and value.resend_from == "AccountManagement@zoqari.com"


@pytest.mark.parametrize("purpose", ["verify", "verify_code", "reset", "invite", "account", "flag"])
def test_submission_preserves_templates_text_html_sender_and_link(purpose):
    requests = []
    value = settings()
    content = "Code: 123456\nhttps://signal.example.test/reset-password#token=synthetic&value=<script>"
    expected = build_message("Zoqari Signal <AccountManagement@zoqari.com>", "recipient@example.test", purpose, content)

    def handler(request):
        requests.append(request)
        assert str(request.url) == "https://api.resend.com/emails"
        assert request.headers["Authorization"] == "Bearer re_synthetic_unit_test_only"
        assert request.extensions["timeout"]["read"] == 15
        payload = json.loads(request.content)
        assert payload == {
            "from": "Zoqari Signal <AccountManagement@zoqari.com>",
            "to": ["recipient@example.test"],
            "subject": str(expected["Subject"]),
            "html": expected.get_body(preferencelist=("html",)).get_content(),
            "text": expected.get_body(preferencelist=("plain",)).get_content(),
        }
        assert "<script>" not in payload["html"]
        assert content in payload["text"]
        return httpx.Response(200, json={"id": "synthetic-submission"})

    ResendMail(value, transport=httpx.MockTransport(handler)).send("recipient@example.test", purpose, content)
    assert len(requests) == 1


@pytest.mark.parametrize("status", [301, 400, 401, 403, 422, 429, 500])
def test_api_failures_do_not_retry_redirect_or_leak(status, caplog):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status,
            text="private-provider-body re_synthetic_unit_test_only",
            headers={"Location": "https://untrusted.example.test"},
        )

    with pytest.raises(MailUnavailable) as error:
        ResendMail(settings(), transport=httpx.MockTransport(handler)).send(
            "recipient@example.test", "reset", "private-reset-token"
        )
    assert len(requests) == 1
    for private in ["private-provider-body", "re_synthetic_unit_test_only", "private-reset-token"]:
        assert private not in str(error.value) and private not in caplog.text


@pytest.mark.parametrize("payload", [{}, {"id": ""}, {"id": None}, [], None])
def test_malformed_success_response_is_uncertain(payload):
    with pytest.raises(MailUnavailable):
        ResendMail(settings(), transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))).send(
            "recipient@example.test", "account", "Synthetic message"
        )


def test_network_error_is_sanitized_and_custom_sender():
    calls = []

    def handler(request):
        calls.append(request)
        assert json.loads(request.content)["from"] == "Zoqari Signal <alerts@example.test>"
        raise httpx.ReadTimeout("private-token-and-request-data")

    with pytest.raises(MailUnavailable) as error:
        ResendMail(settings(resend_from="alerts@example.test"), transport=httpx.MockTransport(handler)).send(
            "recipient@example.test", "flag", "Private alert"
        )
    assert len(calls) == 1 and "private-token" not in str(error.value)


def test_operator_check_is_no_send_and_send_is_explicit(monkeypatch, capsys):
    monkeypatch.setattr(send_test_email, "Settings", lambda: settings())
    factory = Mock()
    monkeypatch.setattr(send_test_email, "build_mail", factory)
    assert send_test_email.main([]) == 0
    assert send_test_email.main(["--send"]) == 1
    factory.assert_not_called()
    assert send_test_email.main(["--to", "recipient@example.test", "--send"]) == 0
    factory.return_value.send.assert_called_once()
    factory.return_value.send.side_effect = RuntimeError("private-provider-detail re_synthetic_unit_test_only")
    assert send_test_email.main(["--to", "recipient@example.test", "--send"]) == 1
    assert "private-provider-detail" not in capsys.readouterr().out


def test_operator_config_failure_never_prints_secret(monkeypatch, capsys):
    monkeypatch.setattr(send_test_email, "Settings", Mock(side_effect=ValueError("re_private_api_key")))
    assert send_test_email.main(["--to", "recipient@example.test", "--send"]) == 1
    assert "re_private_api_key" not in capsys.readouterr().out
