from pydantic import BaseModel, Field, field_validator


class TaskCreateRequest(BaseModel):
    requirement: str = Field(min_length=1, max_length=20_000)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=50)

    @field_validator("requirement")
    @classmethod
    def validate_requirement(cls, value: str) -> str:
        requirement = value.strip()
        if not requirement:
            raise ValueError("requirement cannot be blank")
        return requirement

    @field_validator("acceptance_criteria")
    @classmethod
    def validate_acceptance_criteria(cls, values: list[str]) -> list[str]:
        normalized = [str(value).strip() for value in values]
        if not normalized or any(not value for value in normalized):
            raise ValueError(
                "acceptance_criteria must contain at least one non-empty string"
            )
        if any(len(value) > 4_000 for value in normalized):
            raise ValueError("each acceptance criterion must be at most 4000 characters")
        return normalized
