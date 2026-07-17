from datetime import date
from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

from constant.enums import TransactionType


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    message: str = "ok"
    request_id: str | None = None


class HealthData(BaseModel):
    status: str
    environment: str
    version: str


class TransactionData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: Decimal
    category: str
    description: str | None
    transaction_date: date
    transaction_type: TransactionType


class TransactionPageData(BaseModel):
    items: list[TransactionData]
    total: int
    page: int
    page_size: int


class TransactionDeleteData(BaseModel):
    id: int


class ExpenseCategoryData(BaseModel):
    category: str
    amount: Decimal
    percentage: Decimal


class MonthlyTransactionStatisticsData(BaseModel):
    month: str
    income_total: Decimal
    expense_total: Decimal
    balance: Decimal
    transaction_count: int
    expense_by_category: list[ExpenseCategoryData]
