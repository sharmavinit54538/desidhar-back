import hmac
import hashlib
import json
import razorpay
from app.services.payments.provider import PaymentProvider
from app.core.config import get_settings

settings = get_settings()


class RazorpayPaymentProvider(PaymentProvider):
    def __init__(self, key_id: str = "", key_secret: str = "", webhook_secret: str = ""):
        self.key_id = key_id or settings.RAZORPAY_KEY_ID
        self.key_secret = key_secret or settings.RAZORPAY_KEY_SECRET
        self.webhook_secret = webhook_secret or settings.RAZORPAY_WEBHOOK_SECRET
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = razorpay.Client(auth=(self.key_id, self.key_secret))
        return self._client

    async def create_order(self, amount_paise: int, receipt: str) -> dict:
        order_data = {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt,
            "payment_capture": 1,
        }
        order = self.client.order.create(data=order_data)
        return {
            "provider_order_id": order["id"],
            "amount_paise": order["amount"],
            "currency": order["currency"],
            "receipt": order["receipt"],
        }

    async def verify_payment(self, payload: dict) -> bool:
        provider_order_id = payload.get("razorpay_order_id", "")
        provider_payment_id = payload.get("razorpay_payment_id", "")
        signature = payload.get("razorpay_signature", "")
        if not (provider_order_id and provider_payment_id and signature):
            return False
        return self._verify_signature(provider_order_id, provider_payment_id, signature)

    def _verify_signature(self, order_id: str, payment_id: str, signature: str) -> bool:
        generated_signature = hmac.new(
            self.key_secret.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(generated_signature, signature)

    async def parse_webhook(self, payload: dict, signature: str) -> tuple[bool, str, str, int]:
        if not self._verify_webhook_signature(payload, signature):
            return False, "", "", 0
        event = payload.get("event", "")
        if event != "payment.captured":
            return False, "", "", 0
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        provider_order_id = payment_entity.get("order_id", "")
        provider_payment_id = payment_entity.get("id", "")
        amount_paise = payment_entity.get("amount", 0)
        return True, provider_order_id, provider_payment_id, amount_paise

    def _verify_webhook_signature(self, payload: dict, signature: str) -> bool:
        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            json.dumps(payload, separators=(",", ":")).encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected_signature, signature)

    async def refund_payment(self, provider_payment_id: str, amount_paise: int) -> dict:
        refund = self.client.payment.refund(provider_payment_id, {"amount": amount_paise})
        return {
            "refund_id": refund["id"],
            "amount_paise": refund["amount"],
            "status": refund["status"],
        }

