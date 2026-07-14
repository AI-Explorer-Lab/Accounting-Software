from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from constant.enums import TransactionType
from constant.values import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


class PaginationRequest(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class TransactionCreateRequest(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    category: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    transaction_date: date
    transaction_type: TransactionType

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        category = value.strip()
        if not category:
            raise ValueError("category cannot be blank")
        return category

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        description = value.strip()
        return description or None


class TransactionListRequest(PaginationRequest):
    transaction_type: TransactionType | None = None
    category: str | None = Field(default=None, max_length=100)
    start_date: date | None = None
    end_date: date | None = None
