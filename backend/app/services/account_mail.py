"""Shared account messages with Resend, Graph, TLS SMTP or a private local development outbox."""

import secrets
import os
import smtplib
import ssl
import re
from html import escape
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit


class AccountMail(Protocol):
    def send(self, recipient: str, purpose: str, link: str) -> None: ...


class MailUnavailable(Exception):
    pass


class DisabledMail:
    def send(self, recipient, purpose, link):
        raise MailUnavailable()


class LocalMail:
    def __init__(self, folder: Path):
        self.folder = folder

    def send(self, recipient, purpose, link):
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Credentials: never web-served or logged. Random name prevents overwriting another message.
        path = self.folder / (secrets.token_hex(16) + ".txt")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as message:
            message.write(
                f"LOCAL DEVELOPMENT ONLY — no email was sent.\nTo: {recipient}\nPurpose: {purpose}\n\n{link}\n"
            )


def build_message(sender, recipient, purpose, link):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = {
        "verify": "Verify your Signal email",
        "reset": "Reset your Signal password",
        "invite": "Join your team on Signal",
        "verify_code": "Your Zoqari Signal verification code",
        "flag": "Zoqari Signal: flagged interaction",
        "account": "Zoqari Signal account update",
    }[purpose]
    introduction = (
        "Review this account update. Sign in to Signal through your usual address."
        if purpose == "account"
        else "Review this organization alert securely in Signal."
        if purpose == "flag"
        else "Use this code within 15 minutes to verify your email."
        if purpose == "verify_code"
        else "Open this one-use link to continue."
    )
    content = f"Zoqari Signal\nQuality intelligence for every interaction.\n\n{introduction}\n\n{link}\n\nIf you did not request this account action, ignore it. Never share verification codes or account links."
    message.set_content(content)
    urls = [line.strip() for line in link.splitlines() if line.strip().startswith(("https://", "http://"))]
    url = urls[-1] if urls else None
    button = (
        f'<p><a href="{escape(url, quote=True)}">Continue in Signal</a></p>' if url and urlsplit(url).hostname else ""
    )
    code_match = re.search(r"^Verification code: ([0-9]{6})$", link, re.M) if purpose == "verify_code" else None
    display = (
        f'<p aria-label="Verification code" style="font-size:32px;font-weight:700;letter-spacing:8px;text-align:center">{code_match[1]}</p><p>Expires in 15 minutes. Enter this code only in Zoqari Signal.</p>'
        if code_match
        else f'<div style="white-space:pre-wrap;overflow-wrap:anywhere;padding:18px;background:#f5f8fc">{escape(link)}</div>'
    )
    message.add_alternative(
        f'<html><body style="margin:0;padding:24px;background:#f5f8fc;font-family:Arial,sans-serif;color:#17253a"><main style="max-width:580px;margin:auto;padding:28px;background:white"><h1 style="font-size:22px">Zoqari Signal</h1><p>{escape(introduction)}</p>{display}{button}<p style="font-size:12px">Keep account codes and links private. Contact Zoqari if an account update is unexpected.</p></main></body></html>',
        subtype="html",
    )
    return message


class SMTPMail:
    def __init__(self, settings):
        self.settings = settings

    def send(self, recipient, purpose, link):
        settings = self.settings
        message = build_message(settings.mail_from, recipient, purpose, link)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)


def build_mail(settings):
    if settings.mail_delivery == "resend":
        from .resend_mail import ResendMail

        return ResendMail(settings)
    if settings.mail_delivery == "local":
        return LocalMail(settings.mail_outbox_dir)
    if settings.mail_delivery == "smtp":
        return SMTPMail(settings)
    if settings.mail_delivery == "graph":
        from .graph_mail import GraphMail

        return GraphMail(settings)
    return DisabledMail()
