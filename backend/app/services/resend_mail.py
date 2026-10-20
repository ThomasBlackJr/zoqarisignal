"""Fixed-endpoint Resend transport; shared templates, sanitized failures, no retries."""

import httpx

from .account_mail import MailUnavailable, build_message


class ResendMail:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport

    def send(self, recipient, purpose, link):
        try:
            message = build_message(f"Zoqari Signal <{self.settings.resend_from}>", recipient, purpose, link)
            with httpx.Client(timeout=15, follow_redirects=False, transport=self.transport) as client:
                response = client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": "Bearer " + self.settings.resend_api_key.get_secret_value()},
                    json={
                        "from": str(message["From"]),
                        "to": [recipient],
                        "subject": str(message["Subject"]),
                        "html": message.get_body(preferencelist=("html",)).get_content(),
                        "text": message.get_body(preferencelist=("plain",)).get_content(),
                    },
                )
                if response.status_code != 200:
                    raise MailUnavailable("Email submission unavailable; delivery may be uncertain")
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get("id"), str) or not payload["id"].strip():
                    raise MailUnavailable("Email submission unavailable; delivery may be uncertain")
        except Exception:
            # Do not expose provider bodies, request headers, message data or credentials.
            raise MailUnavailable("Email submission unavailable; delivery may be uncertain") from None
