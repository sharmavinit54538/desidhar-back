from pydantic import BaseModel, ConfigDict


class PaymentMethodOut(BaseModel):
    id: str
    code: str
    name: str
    label: str
    type: str
    enabled: bool
    description: str | None = None
    icon: str | None = None
    min_order: int | None = 0
    max_order: int | None = None
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True)


class PaymentMethodUpdateIn(BaseModel):
    enabled: bool | None = None
    min_order: int | None = None
    max_order: int | None = None
    name: str | None = None
    description: str | None = None
