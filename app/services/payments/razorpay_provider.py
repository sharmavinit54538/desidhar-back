from app.services.payments.provider import PaymentProvider


class RazorpayPaymentProvider(PaymentProvider):
    def __init__(self, key_id: str = "", key_secret: str = ""):
        self.key_id = key_id
        self.key_secret = key_secret

    async def create_order(self, amount_paise: int, receipt: str) -> dict:
        raise NotImplementedError("Razorpay adapter placeholder")

    async def verify_payment(self, payload: dict) -> bool:
        raise NotImplementedError("Razorpay adapter placeholder")

    async def parse_webhook(self, payload: dict, signature: str) -> tuple[bool, str, str, int]:
        raise NotImplementedError("Razorpay adapter placeholder")
