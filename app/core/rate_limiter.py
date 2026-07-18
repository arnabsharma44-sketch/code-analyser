from collections import defaultdict, deque
import threading
from time import monotonic

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, rate_limit: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.rate_limit = rate_limit
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    async def dispatch(self, request: Request, call_next):
        client_key = self._get_client_identifier(request)
        allowed, remaining, reset_after = self._record_request(client_key)

        headers = {
            "X-RateLimit-Limit": str(self.rate_limit),
            "X-RateLimit-Remaining": str(max(0, remaining)),
            "X-RateLimit-Reset": str(int(reset_after)),
        }

        if not allowed:
            headers["Retry-After"] = str(int(reset_after))
            return JSONResponse(
                {"detail": "Rate limit exceeded. Try again later."},
                status_code=429,
                headers=headers,
            )

        response = await call_next(request)
        response.headers.update(headers)
        return response

    def _get_client_identifier(self, request: Request) -> str:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip()

        client = request.client
        if client is not None and client.host:
            return client.host

        return "unknown"

    def _record_request(self, client_key: str) -> tuple[bool, int, float]:
        now = monotonic()
        with self._lock:
            queue = self._requests[client_key]
            while queue and queue[0] <= now - self.window_seconds:
                queue.popleft()

            if len(queue) >= self.rate_limit:
                reset_after = queue[0] + self.window_seconds - now
                return False, 0, max(reset_after, 0.0)

            queue.append(now)
            remaining = self.rate_limit - len(queue)
            reset_after = self.window_seconds
            return True, remaining, reset_after
