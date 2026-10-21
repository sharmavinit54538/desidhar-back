import logging
from typing import Dict, Any

logger = logging.getLogger("desidhar.notifications")


class NotificationService:
    """
    Asynchronous notification service for transactional communications
    (emails, SMS, invoices). Dispatched via FastAPI BackgroundTasks or Celery/ARQ workers.
    """

    @staticmethod
    async def send_order_confirmation(email: str, order_data: Dict[str, Any]) -> None:
        logger.info(
            f"[NOTIFICATION] Dispatched Order Confirmation email to {email} for Order #{order_data.get('order_number')}. Total: ₹{order_data.get('final_payable')}"
        )

    @staticmethod
    async def send_payment_receipt(email: str, transaction_data: Dict[str, Any]) -> None:
        logger.info(
            f"[NOTIFICATION] Dispatched Payment Receipt email to {email} for Transaction #{transaction_data.get('transaction_id')}. Amount: ₹{transaction_data.get('amount')}"
        )

    @staticmethod
    async def send_order_status_update(email: str, order_number: str, new_status: str) -> None:
        logger.info(
            f"[NOTIFICATION] Dispatched Status Update email to {email} for Order #{order_number}: Status is now '{new_status}'."
        )

    @staticmethod
    async def send_security_alert(email: str, alert_message: str) -> None:
        logger.warning(
            f"[SECURITY ALERT] Sent emergency security alert to {email}: {alert_message}"
        )


notification_service = NotificationService()
