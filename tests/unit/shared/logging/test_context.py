"""Tests for request-id correlation via contextvars (async-safe propagation)."""

import asyncio

from src.shared.logging.context import (
    bind_request_id,
    clear_request_id,
    get_request_id,
    new_request_id,
)


class TestRequestIdBinding:
    def teardown_method(self) -> None:
        clear_request_id()

    def test_new_request_id_is_unique_nonempty(self) -> None:
        a, b = new_request_id(), new_request_id()
        assert a and b and a != b

    def test_bind_returns_and_sets_id(self) -> None:
        rid = bind_request_id("req-123")
        assert rid == "req-123"
        assert get_request_id() == "req-123"

    def test_bind_without_arg_generates_id(self) -> None:
        rid = bind_request_id()
        assert rid
        assert get_request_id() == rid

    def test_get_returns_none_before_bind(self) -> None:
        clear_request_id()
        assert get_request_id() is None

    def test_clear_removes_id(self) -> None:
        bind_request_id("x")
        clear_request_id()
        assert get_request_id() is None


class TestAsyncPropagation:
    def test_id_visible_in_nested_coroutine(self) -> None:
        async def inner() -> str | None:
            return get_request_id()

        async def outer() -> str | None:
            bind_request_id("outer-id")
            return await inner()

        assert asyncio.run(outer()) == "outer-id"

    def test_concurrent_tasks_isolated(self) -> None:
        async def worker(rid: str) -> str | None:
            bind_request_id(rid)
            await asyncio.sleep(0.01)
            return get_request_id()

        async def main() -> list[str | None]:
            return await asyncio.gather(
                asyncio.create_task(worker("a")),
                asyncio.create_task(worker("b")),
            )

        assert sorted(x for x in asyncio.run(main()) if x) == ["a", "b"]
