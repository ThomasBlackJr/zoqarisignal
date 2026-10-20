"""Explicit one-message operator test. Never imports the app, connects to a DB or prints secrets."""

import argparse

from app.account_schemas import Email
from app.config import Settings
from app.services.account_mail import build_mail


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate Resend configuration; send only with --send and --to.")
    parser.add_argument("--to", help="Recipient you authorize for one test message")
    parser.add_argument("--send", action="store_true", help="Submit one real external test email")
    args = parser.parse_args(argv)
    try:
        settings = Settings()
        if settings.mail_delivery != "resend":
            raise ValueError()
        if not args.send:
            print("Resend configuration is valid. No email sent. Use --to ADDRESS --send for one real test.")
            return 0
        if not args.to:
            raise ValueError()
        recipient = Email(email=args.to).email
    except Exception:
        print("Configuration invalid. Check MAIL_DELIVERY=resend, RESEND_API_KEY, RESEND_FROM and recipient locally.")
        return 1
    try:
        build_mail(settings).send(
            recipient, "account", "This is an explicitly requested Zoqari Signal transactional email test."
        )
    except Exception:
        print("Submission failed or is uncertain. Check the provider dashboard before explicitly retrying.")
        return 1
    print("Resend accepted one test message. Acceptance does not prove delivery; check the recipient inbox/dashboard.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
