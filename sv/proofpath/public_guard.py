"""Single-process quotas for the fictional public demo, not production identity."""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .auth import SESSION_COOKIE


class PublicGuard(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.ip_requests = defaultdict(deque)
        self.session_counts = defaultdict(lambda: defaultdict(int))
        self.session_seen = {}
        self.model_requests = deque()
        self.hourly_cap = int(os.getenv("PROOFPATH_MODEL_HOURLY_CAP", "60"))
        self.last_cleanup = 0.0

    @staticmethod
    def limited(code, message, retry_after=60):
        return JSONResponse(
            {"schema_version": 1, "error": {"code": code, "message": message,
             "details": {"retry_after_seconds": retry_after}}},
            status_code=429, headers={"Retry-After": str(retry_after)},
        )

    async def dispatch(self, request, call_next):
        now = time.monotonic()
        if now - self.last_cleanup > 60:
            self.last_cleanup = now
            for key in list(self.ip_requests):
                if not self.ip_requests[key] or self.ip_requests[key][-1] < now - 60:
                    del self.ip_requests[key]
            for key, seen in list(self.session_seen.items()):
                if seen < now - 86400:
                    self.session_seen.pop(key, None)
                    self.session_counts.pop(key, None)
        # Health probes must not consume a shared proxy's quota. Do not trust
        # forwarded headers here: configure Uvicorn's trusted proxy explicitly.
        if request.url.path == "/health":
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        window = self.ip_requests[ip]
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= 60:
            return self.limited("rate_limit", "Public demo request limit reached.")
        window.append(now)
        path = request.url.path.rstrip("/")
        kind = None
        if request.method == "POST":
            if path == "/api/v1/evaluations":
                kind = "evaluations"
            elif path.startswith("/api/v1/evaluations/") and path.endswith("/runs"):
                kind = "poc_runs"
            elif path.startswith("/api/v1/evaluations/") and path.endswith("/agent-evaluation"):
                kind = "agent_evaluations"
        if kind:
            # Install before the session_cookie decorator so it runs inside it.
            sid = request.cookies.get(SESSION_COOKIE) or getattr(request.state, "new_session", None)
            if not sid:
                return JSONResponse({"schema_version": 1, "error": {
                    "code": "session_required", "message": "Open the demo homepage first.",
                    "details": {}}}, status_code=401)
            self.session_seen[sid] = now
            caps = {"evaluations": 5, "poc_runs": 3, "agent_evaluations": 2}
            if self.session_counts[sid][kind] >= caps[kind]:
                return self.limited("session_limit", f"Public demo {kind} limit reached.", 86400)
            model_backed = kind in {"evaluations", "agent_evaluations"}
            while self.model_requests and self.model_requests[0] <= now - 3600:
                self.model_requests.popleft()
            if model_backed and len(self.model_requests) >= self.hourly_cap:
                return self.limited("model_budget", "Public demo hourly model budget reached.", 3600)
            # Reserve before awaiting: simultaneous requests cannot exceed quotas.
            # Attempts count even when validation or downstream execution fails.
            self.session_counts[sid][kind] += 1
            if model_backed:
                self.model_requests.append(now)
        return await call_next(request)


def install(app):
    """Call immediately after FastAPI creation, before session middleware."""
    if os.getenv("PROOFPATH_DEMO_MODE") == "public":
        app.add_middleware(PublicGuard)
