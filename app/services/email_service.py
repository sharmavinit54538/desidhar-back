import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def send_otp_email(email: str, otp: str) -> None:
    if settings.APP_ENV == "dev" and not settings.smtp_configured:
        print(f"[DEV] OTP for {email}: {otp}")
        return

    if not settings.smtp_configured:
        logger.warning("SMTP not configured, skipping email send")
        return

    msg = MIMEMultipart()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = email
    msg["Subject"] = "Your DesiDhar OTP Code"
    body = f"Your OTP code is: {otp}\n\nThis code expires in 5 minutes."
    msg.attach(MIMEText(body, "plain"))

    try:
        if settings.SMTP_TLS:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)
    except Exception as e:
        logger.error(f"Failed to send OTP email: {e}")
        raise