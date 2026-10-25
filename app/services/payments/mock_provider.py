import uuid
from app.services.payments.provider import PaymentProvider


class MockPaymentProvider(PaymentProvider):
    async def create_order(self, amount_paise: int, receipt: str) -> dict:
        p_order_id = f"mock_ord_{uuid.uuid4().hex[:12]}"
        return {"provider_order_id": p_order_id, "amount_paise": amount_paise, "currency": "INR", "receipt": receipt}

    async def verify_payment(self, payload: dict) -> bool:
        p_ord = payload.get("provider_order_id", "")
        sig = payload.get("signature", "")
        return sig == f"mock_sig_{p_ord}"

    async def parse_webhook(self, payload: dict, signature: str) -> tuple[bool, str, str, int]:
        p_ord = payload.get("provider_order_id", "")
        p_pay = payload.get("provider_payment_id", f"mock_pay_{uuid.uuid4().hex[:8]}")
        amt = payload.get("amount_paise", 0)
        valid = signature == f"mock_sig_{p_ord}"
        return valid, p_ord, p_pay, amt
