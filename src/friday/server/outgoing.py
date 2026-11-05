"""Mail a hosted Friday sends (H27): sign-in links, from you@gmail.com through Gmail's SMTP with an
app password. The password comes from the environment (FRIDAY_SMTP_PASSWORD), put there when the service starts from
Bitwarden (H82, scripts/server/with-secrets.sh), so Friday never knows where secrets are kept. FRIDAY_MAIL_OUTBOX
names a folder where mail is written instead of sent: tests, and a copy with no password yet.
"""

import os
import smtplib
import ssl
import time
from email.message import EmailMessage
from pathlib import Path

SENDER = "you@gmail.com"
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 587


class MailError(Exception):
    """Mail couldn't be sent; the message says why in words for the page."""


def signin_message(to: str, link: str, code: str) -> EmailMessage:
    """The code leads the subject, so a notification or the inbox's list shows it without opening the email (H92)."""
    message = EmailMessage()
    message["From"] = f"Friday <{os.environ.get('FRIDAY_MAIL_FROM', SENDER)}>"
    message["To"] = to
    message["Subject"] = f"{code} is your Friday sign-in code"
    message.set_content(
        f"Your code to sign in to Friday: {code}\n\n"
        "Type it on the page where you asked, or open this link instead:\n\n"
        f"{link}\n\n"
        "Either one works once, for the next 15 minutes.\n\n"
        "If you didn't ask to sign in, ignore this email: nobody gets in without the code or the link."
    )
    return message


def send(message: EmailMessage) -> None:
    outbox = os.environ.get("FRIDAY_MAIL_OUTBOX")
    if outbox:
        folder = Path(outbox)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{time.time_ns()}.eml").write_bytes(bytes(message))
        return
    password = os.environ.get("FRIDAY_SMTP_PASSWORD")
    if not password:
        raise MailError("This Friday can't send mail yet: its Gmail app password isn't set up.")
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(os.environ.get("FRIDAY_MAIL_FROM", SENDER), password)
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as error:
        raise MailError(f"Gmail didn't take the email ({type(error).__name__}); try again in a minute.") from error
