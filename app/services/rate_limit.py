"""进程内滑动窗口限流器（单机部署够用；多机中继场景可替换为 Redis）。

用法：
    from app.services.rate_limit import limiter
    if not limiter.allow(key, limit, window_seconds):
        return 429

线程安全（GIL + 显式锁），并做容量清理防止 key 无限膨胀。
"""
import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    _MAX_KEYS = 20000  # key 数量上限，超出时清理过期/空队列

    def __init__(self):
        self._lock = threading.Lock()
        self._hits = defaultdict(deque)

    def allow(self, key, limit, window_seconds):
        """窗口内是否还允许一次请求。limit<=0 视为不限。"""
        if limit <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            queue = self._hits[key]
            while queue and now - queue[0] > window_seconds:
                queue.popleft()
            if len(queue) >= limit:
                return False
            queue.append(now)
            self._maybe_cleanup()
            return True

    def _maybe_cleanup(self):
        if len(self._hits) <= self._MAX_KEYS:
            return
        for key in [k for k, v in self._hits.items() if not v]:
            del self._hits[key]
        if len(self._hits) > self._MAX_KEYS:
            # 极端情况下按插入顺序淘汰最旧的一半
            keys = list(self._hits.keys())[: self._MAX_KEYS // 2]
            for key in keys:
                del self._hits[key]


limiter = RateLimiter()
