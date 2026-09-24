import secrets
import time
from fastapi import HTTPException
from sqlalchemy import select, update, delete
from ..auth import hasher, token_hash, verify
from ..models import User, VerificationCode, AccountToken
from ..logging import event


def issue_code(db, user, request):
    db.execute(update(User).where(User.id == user.id).values(active=User.active))
    old = db.get(VerificationCode, user.id, populate_existing=True)
    now = time.time()
    if old and old.sent_at > now - 60:
        raise HTTPException(
            429,
            "Wait 60 seconds before requesting another code.",
            headers={"Retry-After": str(max(1, int(old.sent_at + 60 - now)))},
        )
    code = f"{secrets.randbelow(1000000):06d}"
    challenge = secrets.token_urlsafe(32)
    row = old or VerificationCode(user_id=user.id)
    row.challenge_hash, row.code_hash = token_hash(challenge), hasher.hash(code)
    row.sent_at, row.expires_at, row.attempts = now, now + 900, 0
    db.add(row)
    # Resend replaces previously-issued verification links too; recovery/invitations untouched.
    db.execute(delete(AccountToken).where(AccountToken.user_id == user.id, AccountToken.purpose == "verify"))
    try:
        request.app.state.mail.send(
            user.email,
            "verify_code",
            f"Verification code: {code}\n\nExpires in 15 minutes. Enter it only in Zoqari Signal.",
        )
    except Exception as exc:
        event("verification_mail_failed", error_type=type(exc).__name__)
        raise HTTPException(503, "Verification email could not be submitted. Try again later.") from None
    return challenge


def redeem_code(db, code, challenge=None, user=None):
    row = (
        db.scalar(select(VerificationCode).where(VerificationCode.challenge_hash == token_hash(challenge)))
        if challenge
        else (db.get(VerificationCode, user.id) if user else None)
    )
    if row is None:
        raise HTTPException(400, "Code is invalid, expired or already used. Request a new code.")
    uid = row.user_id
    db.execute(update(User).where(User.id == uid).values(active=User.active))
    db.expire_all()
    row = db.get(VerificationCode, uid)
    user = db.get(User, uid)
    if (
        not row
        or not user.active
        or user.email_verified
        or row.expires_at <= time.time()
        or row.attempts >= 5
        or (challenge and row.challenge_hash != token_hash(challenge))
    ):
        raise HTTPException(400, "Code is invalid, expired or already used. Request a new code.")
    row.attempts += 1
    if not verify(code, row.code_hash):
        db.commit()  # Failed attempts must survive the error response.
        raise HTTPException(400, "Code is invalid, expired or already used. Request a new code.")
    user.email_verified = True
    db.delete(row)
    db.execute(delete(AccountToken).where(AccountToken.user_id == uid, AccountToken.purpose == "verify"))
    return user
