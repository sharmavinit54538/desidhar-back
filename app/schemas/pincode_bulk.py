from pydantic import BaseModel, Field


class BulkRowError(BaseModel):
    row: int
    pincode: str | None = None
    reason: str


class BulkUpsertResult(BaseModel):
    created: int
    updated: int
    invalid: int
    errors: list[BulkRowError] = Field(default_factory=list)

