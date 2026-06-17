"""Опциональная защита API дашборда (пароль или legacy-токен)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from business_dashboard.config import DASHBOARD_PASSWORD, DASHBOARD_TOKEN, dashboard_auth_enabled


_PUBLIC_PREFIXES = (
    "/static/",
    "/mini",
    "/webhook",
    "/health",
    "/api/config",
    "/api/mini/",
)


def _auth_ok(request: Request) -> bool:
    pw = request.headers.get("X-Dashboard-Password", "").strip()
    if DASHBOARD_PASSWORD and pw == DASHBOARD_PASSWORD:
        return True
    token = request.headers.get("X-Dashboard-Token", "").strip()
    if DASHBOARD_TOKEN and token == DASHBOARD_TOKEN:
        return True
    if request.url.path.startswith("/api/remote/worker/"):
        from remote_agent.config import REMOTE_WORKER_SECRET

        secret = request.headers.get("X-Remote-Worker-Secret", "").strip()
        if REMOTE_WORKER_SECRET and secret == REMOTE_WORKER_SECRET:
            return True
    return False


class DashboardAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not dashboard_auth_enabled():
            return await call_next(request)
        path = request.url.path
        if path == "/" or any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)
        if path.startswith("/api/"):
            if not _auth_ok(request):
                return JSONResponse({"detail": "Неверный пароль"}, status_code=401)
        return await call_next(request)
