import json

import httpx
import pytest

from app.config import Settings
from app.services.account_mail import build_mail, LocalMail, MailUnavailable
from app.services.graph_mail import GraphMail


def settings(**values):
    return Settings(
        _env_file=None,
        mail_delivery="graph",
        m365_tenant_id="11111111-1111-1111-1111-111111111111",
        m365_client_id="22222222-2222-2222-2222-222222222222",
        m365_client_secret="synthetic-application-secret",
        **values,
    )


def test_graph_configuration_production_and_provider_selection(tmp_path):
    value = settings(
        environment="production",
        database_url="postgresql://fixture@localhost/test",
        frontend_origin="https://signal.example.test",
        cookie_secure=True,
    )
    assert isinstance(build_mail(value), GraphMail)
    assert value.m365_sender == "accountmanagement@zoqari.com"
    assert "synthetic-application-secret" not in repr(value)
    assert "synthetic-application-secret" not in value.model_dump_json()
    local = Settings(_env_file=None, mail_delivery="local", mail_outbox_dir=tmp_path)
    assert isinstance(build_mail(local), LocalMail)
    for purpose in ("verify", "verify_code", "reset", "invite", "account"):
        build_mail(local).send("fixture@example.test", purpose, "Synthetic message only")
    assert len(list(tmp_path.glob("*.txt"))) == 5


@pytest.mark.parametrize(
    "values",
    [
        {"m365_tenant_id": ""},
        {"m365_client_id": ""},
        {"m365_client_secret": ""},
        {"m365_tenant_id": "../../unexpected"},
        {"m365_sender": "invalid"},
    ],
)
def test_graph_missing_or_invalid_configuration_fails_closed(values):
    base = {
        "m365_tenant_id": "11111111-1111-1111-1111-111111111111",
        "m365_client_id": "22222222-2222-2222-2222-222222222222",
        "m365_client_secret": "synthetic-secret",
    }
    with pytest.raises(ValueError):
        Settings(_env_file=None, mail_delivery="graph", **{**base, **values})


def test_graph_oauth_cache_templates_and_fixed_sender():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.host == "login.microsoftonline.com":
            assert b"grant_type=client_credentials" in request.content
            return httpx.Response(200, json={"access_token": "synthetic-access-token", "expires_in": 3600})
        assert request.url.host == "graph.microsoft.com"
        assert "accountmanagement%40zoqari.com" in str(request.url)
        payload = json.loads(request.content)
        assert payload["saveToSentItems"] is True
        assert payload["message"]["toRecipients"][0]["emailAddress"]["address"] == "recipient@example.test"
        assert "Microsoft" not in payload["message"]["subject"]
        assert "<script>" not in payload["message"]["body"]["content"]
        return httpx.Response(202)

    mail = GraphMail(settings(), transport=httpx.MockTransport(handler))
    for purpose in ("verify", "reset", "invite", "account"):
        mail.send("recipient@example.test", purpose, "Synthetic <script>untrusted</script>")
    assert len([r for r in requests if r.url.host == "login.microsoftonline.com"]) == 1
    assert len(requests) == 5
    mail._expires = 0
    mail.send("recipient@example.test", "reset", "Synthetic")
    assert len(requests) == 7


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_graph_failure_is_safe_and_never_automatically_resends(status):
    sends = []

    def handler(request):
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "synthetic-token", "expires_in": 3600})
        sends.append(request)
        return httpx.Response(status, text="private-provider-response synthetic-secret")

    mail = GraphMail(settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(MailUnavailable) as error:
        mail.send("fixture@example.test", "reset", "private-reset-link")
    assert "private-provider-response" not in str(error.value)
    assert "private-reset-link" not in str(error.value)
    assert len(sends) == 1


def test_graph_auth_failure_never_sends_mail():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400, text="private-credential-detail")

    with pytest.raises(MailUnavailable) as error:
        GraphMail(settings(), transport=httpx.MockTransport(handler)).send("fixture@example.test", "verify", "private")
    assert "private-credential-detail" not in str(error.value)
    assert len(calls) == 1
