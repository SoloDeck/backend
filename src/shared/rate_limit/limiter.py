"""In-process fixed-window rate limiter.

A deliberately small, dependency-free guard for public (unauthenticated)
endpoints. It tracks recent hit timestamps per key inside the worker process.

Scope and caveats:
- Per-process only. Behind multiple workers/replicas each process keeps its own
  window, so the effective limit is `max_requests * num_processes`. For a hard,
  cluster-wide cap, layer a gateway/Redis limit on top — this class is the
  "rate-limit cơ bản" (basic) application-layer guard, not the last line.
- The clock is injectable (`time_func`) so the window logic is unit-testable
  without sleeping.
"""

import threading
import time
from collections.abc import Callable

from src.shared.exceptions.domain import RateLimitError


class FixedWindowRateLimiter:
    """Allow at most `max_requests` per `window_seconds` for each key."""

    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        time_func: Callable[[], float] = time.monotonic,
        max_keys_before_sweep: int = 10_000,
        thong_bao: str | None = None,
    ) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._max = max_requests
        self._window = window_seconds
        self._time = time_func
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        # Ngưỡng quét dọn. Xem `_don_khoa_het_han`.  #Huynh
        self._nguong_don = max_keys_before_sweep
        # Câu này đi thẳng ra màn hình người dùng qua handler 429, nên phải là tiếng Việt
        # và phải nói được PHẢI LÀM GÌ TIẾP. Mỗi cửa một câu riêng vì "thử lại sau" ở cửa
        # đăng nhập và ở cửa gửi biểu mẫu là hai chuyện khác nhau.  #Huynh
        self._thong_bao = thong_bao or (
            "Bạn thao tác hơi nhanh. Chờ một lát rồi thử lại giúp mình nhé."
        )

    def check(self, key: str) -> None:
        """Record a hit for `key`; raise RateLimitError if the window is full.

        Expired timestamps are pruned on each call so memory for an idle key is
        reclaimed the next time it is touched.
        """
        now = self._time()
        cutoff = now - self._window
        with self._lock:
            recent = [t for t in self._hits.get(key, []) if t > cutoff]
            if len(recent) >= self._max:
                self._hits[key] = recent
                raise RateLimitError(self._thong_bao)
            recent.append(now)
            self._hits[key] = recent
            if len(self._hits) > self._nguong_don:
                self._don_khoa_het_han(cutoff)

    def _don_khoa_het_han(self, cutoff: float) -> None:
        """Xoá những khoá mà mọi dấu thời gian đều đã hết hạn.

        Vì sao cần: `check` chỉ dọn dấu thời gian của ĐÚNG khoá đang được gọi, nên một
        khoá không bao giờ được chạm lại sẽ nằm trong `_hits` mãi mãi. Mà khoá ở đây do
        người ngoài đặt — token chia sẻ trong URL, địa chỉ IP — nên người lạ chỉ cần bắn
        vào những link bịa, mỗi lần một chuỗi khác nhau, là bơm được từ điển này phình
        tới hết RAM tiến trình. Quét dọn khi số khoá vượt ngưỡng thì chi phí chia đều,
        không đụng vào đường đi thông thường.

        Gọi trong khi đang giữ `_lock`.  #Huynh
        """
        het_han = [k for k, v in self._hits.items() if not v or max(v) <= cutoff]
        for k in het_han:
            del self._hits[k]

    def reset(self, key: str | None = None) -> None:
        """Clear tracked hits for one key, or all keys when `key` is None."""
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)
