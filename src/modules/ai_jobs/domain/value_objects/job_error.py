from dataclasses import dataclass


@dataclass(frozen=True)
class JobError:
    """Shape stored in AiJobModel.error (JSONB) when a job ends in `failed`.

    `retryable` tells the caller whether creating a new job for the same
    entity is likely to succeed (transient LLM/network failure) versus
    pointless until something changes (not found, entitlement, validation).
    """

    code: str
    message: str
    retryable: bool

    def to_dict(self) -> dict[str, str | bool]:
        return {"code": self.code, "message": self.message, "retryable": self.retryable}
