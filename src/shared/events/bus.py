"""Lightweight in-process event bus for domain events.

Usage:
    bus = EventBus()
    bus.subscribe("deals.stage_changed", handler)
    await bus.publish("deals.stage_changed", payload)

For cross-process fanout, publish to Redis Streams or Celery tasks instead.
"""

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class EventBus:
    _handlers: dict[str, list[EventHandler]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            return
        log.debug("event.published", event_type=event_type, handler_count=len(handlers))
        await asyncio.gather(
            *[handler(payload) for handler in handlers],
            return_exceptions=True,
        )


# Module-level singleton — replace with DI container binding in production.
event_bus = EventBus()
