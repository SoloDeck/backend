from enum import StrEnum


class AiJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES: frozenset[AiJobStatus] = frozenset(
    {AiJobStatus.SUCCEEDED, AiJobStatus.FAILED, AiJobStatus.CANCELLED}
)

# Allowed forward transitions per status. A job can be cancelled while queued
# (before a worker picks it up) or while running (best-effort — the worker
# checks this flag before writing its result, it cannot be force-killed
# mid-LLM-call).
STATUS_TRANSITIONS: dict[AiJobStatus, frozenset[AiJobStatus]] = {
    AiJobStatus.QUEUED: frozenset({AiJobStatus.RUNNING, AiJobStatus.CANCELLED}),
    AiJobStatus.RUNNING: frozenset(
        {AiJobStatus.SUCCEEDED, AiJobStatus.FAILED, AiJobStatus.CANCELLED}
    ),
    AiJobStatus.SUCCEEDED: frozenset(),
    AiJobStatus.FAILED: frozenset(),
    AiJobStatus.CANCELLED: frozenset(),
}


def can_transition(current: AiJobStatus, target: AiJobStatus) -> bool:
    return target in STATUS_TRANSITIONS[current]
