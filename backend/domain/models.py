from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CurrentUser:
    subject: str
    roles: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class UseCaseResult:
    name: str
    status: str
    actor: str
