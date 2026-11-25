import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def send_otp_email(email: str, otp: str) -> None:
    if settings.APP_ENV == "dev" and not settings.smtp_configured:
        logger.info("OTP generated for %s (dev mode, email dispatch simulated)", email)
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


async def send_delivery_otp_email(email: str, otp: str, order_number: str) -> None:
    """Send a delivery-only confirmation code; never log or return its value."""
    if not settings.smtp_configured:
        raise RuntimeError("SMTP is required to send delivery verification codes")
    msg = MIMEMultipart()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = email
    msg["Subject"] = f"Confirm delivery for {order_number}"
    msg.attach(MIMEText(
        f"Your DesiDhar delivery confirmation code for order {order_number} is {otp}. "
        "Share it only after you have received the parcel. This code expires in 10 minutes.", "plain"))
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
        logger.error("Failed to send delivery verification email: %s", type(e).__name__)
        raise


async def send_order_email(email: str, subject: str, body: str) -> None:
    """Send customer order lifecycle email using the configured SMTP transport."""
    if not settings.smtp_configured:
        raise RuntimeError("SMTP is not configured")
    msg = MIMEMultipart()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = email
    msg["Subject"] = subject
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
        logger.error("Failed to send order lifecycle email: %s", type(e).__name__)
        raise
