from enum import StrEnum


class TaskOwner(StrEnum):
    """Polymorphic owner type of a task (the `entity_type` column)."""

    PROJECT = "project"
    DEAL = "deal"
    REMINDER = "reminder"
