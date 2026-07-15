from enum import StrEnum


class ApiTaskStatus(StrEnum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    SUCCESS = "success"
    MANUAL_REVIEW = "manual_review"
    INFRASTRUCTURE_ERROR = "infrastructure_error"


class ErrorCode(StrEnum):
    BUSINESS_ERROR = "BUSINESS_ERROR"
    INVALID_TASK_ID = "INVALID_TASK_ID"
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    TASK_CONFLICT = "TASK_CONFLICT"
    TASK_NOT_READY = "TASK_NOT_READY"
    INTERNAL_ERROR = "INTERNAL_ERROR"
