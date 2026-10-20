"""App-only Microsoft Graph mail; fixed trusted endpoints, private token cache, no send retries."""

import threading
import time
from urllib.parse import quote

import httpx

from .account_mail import MailUnavailable, build_message


class GraphMail:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport
        self._token = None
        self._expires = 0
        self._lock = threading.Lock()

    def _access_token(self, client):
        with self._lock:
            if self._token and time.monotonic() < self._expires:
                return self._token
            response = client.post(
                f"https://login.microsoftonline.com/{self.settings.m365_tenant_id}/oauth2/v2.0/token",
                data={
                    "client_id": self.settings.m365_client_id,
                    "client_secret": self.settings.m365_client_secret.get_secret_value(),
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials",
                },
            )
            if response.status_code != 200:
                raise MailUnavailable("Microsoft application authentication unavailable")
            payload = response.json()
            token, lifetime = payload.get("access_token"), payload.get("expires_in")
            if (
                not isinstance(token, str)
                or not token
                or not isinstance(lifetime, (int, float))
                or not 60 < lifetime <= 86400
            ):
                raise MailUnavailable("Microsoft application authentication unavailable")
            self._token, self._expires = token, time.monotonic() + lifetime - 60
            return token

    def send(self, recipient, purpose, link):
        message = build_message(self.settings.m365_sender, recipient, purpose, link)
        try:
            with httpx.Client(timeout=15, follow_redirects=False, transport=self.transport) as client:
                token = self._access_token(client)
                response = client.post(
                    f"https://graph.microsoft.com/v1.0/users/{quote(self.settings.m365_sender, safe='')}/sendMail",
                    headers={"Authorization": "Bearer " + token},
                    json={
                        "message": {
                            "subject": str(message["Subject"]),
                            "body": {
                                "contentType": "HTML",
                                "content": message.get_body(preferencelist=("html",)).get_content(),
                            },
                            "toRecipients": [{"emailAddress": {"address": recipient}}],
                        },
                        "saveToSentItems": True,
                    },
                )
                if response.status_code == 401:
                    with self._lock:
                        self._token, self._expires = None, 0
                if response.status_code != 202:
                    raise MailUnavailable("Microsoft mail submission unavailable; delivery may be uncertain")
        except MailUnavailable:
            raise
        except Exception:
            # Never expose HTTP response text, auth headers, message payloads or credentials.
            raise MailUnavailable("Microsoft mail submission unavailable; delivery may be uncertain") from None
