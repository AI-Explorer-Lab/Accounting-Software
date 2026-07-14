from enum import StrEnum


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class TransactionType(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"


class ErrorCode(StrEnum):
    BUSINESS_ERROR = "BUSINESS_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
