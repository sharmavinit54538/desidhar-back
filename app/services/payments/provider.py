from abc import ABC, abstractmethod


class PaymentProvider(ABC):
    @abstractmethod
    async def create_order(self, amount_paise: int, receipt: str) -> dict:
        pass

    @abstractmethod
    async def verify_payment(self, payload: dict) -> bool:
        pass

    @abstractmethod
    async def parse_webhook(self, payload: dict, signature: str) -> tuple[bool, str, str, int]:
        pass
