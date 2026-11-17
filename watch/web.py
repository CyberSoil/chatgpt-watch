"""Same-origin private PWA and REST endpoints for the Watch queue."""
from __future__ import annotations

import json
import os
from pathlib import Path
import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

ROOT = Path(__file__).parent / "static"
PUBLIC_PATHS = {"/", "/health", "/app.css", "/app.js", "/sw.js",
                "/manifest.webmanifest", "/icon.svg", "/favicon.ico"}
MIMES = {"index.html": "text/html; charset=utf-8",
         "app.css": "text/css; charset=utf-8",
         "app.js": "text/javascript; charset=utf-8",
         "sw.js": "text/javascript; charset=utf-8",
         "manifest.webmanifest": "application/manifest+json",
         "icon.svg": "image/svg+xml"}


class WatchAuthMiddleware(BaseHTTPMiddleware):
    """Only static PWA shell and health are public; private API and MCP need Bearer."""
    def __init__(self, app):
        super().__init__(app)
        self.token = os.getenv("MCP_AUTH_TOKEN", "")
        if len(self.token) < 24:
            raise RuntimeError("Set MCP_AUTH_TOKEN to a random string of at least 24 chars")

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path not in PUBLIC_PATHS:
            authorization = request.headers.get("authorization", "")
            if not hmac.compare_digest(authorization, "Bearer " + self.token):
                return JSONResponse({"error": "unauthorized",
                                     "message": "Неверный ключ доступа."}, status_code=401,
                                    headers={"Cache-Control": "no-store"})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; manifest-src 'self'; "
            "worker-src 'self'; font-src 'self'; base-uri 'none'; "
            "object-src 'none'; frame-ancestors 'none'; form-action 'self'")
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response


def web_routes(queue):
    def asset(filename):
        async def handler(request: Request):
            headers = {"Cache-Control": "no-cache"}
            if filename == "sw.js":
                headers = {"Cache-Control": "no-store", "Service-Worker-Allowed": "/"}
            return FileResponse(ROOT / filename, media_type=MIMES[filename], headers=headers)
        return handler

    async def start(request: Request):
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            return JSONResponse({"message": "Ожидается JSON."}, status_code=415)
        data = await request.body()
        if len(data) > 8192:
            return JSONResponse({"message": "Слишком большой запрос."}, status_code=413)
        try:
            payload = json.loads(data)
            if not isinstance(payload, dict):
                raise ValueError("Нужен JSON-объект.")
            result = queue.start(url=payload.get("url", ""),
                                 question=payload.get("question", "О чём говорится в видео?"),
                                 detail=payload.get("detail", "balanced"))
        except (ValueError, TypeError) as exc:
            return JSONResponse({"status": "invalid_input", "message": str(exc)}, status_code=400)
        return JSONResponse(result, status_code=429 if result.get("status") == "busy" else
                            (202 if result.get("status") == "processing" else 200))

    async def result(request: Request):
        return JSONResponse(queue.result(request.path_params["job_id"], wait_seconds=0))

    return [
        Route("/", asset("index.html")),
        Route("/app.css", asset("app.css")),
        Route("/app.js", asset("app.js")),
        Route("/sw.js", asset("sw.js")),
        Route("/manifest.webmanifest", asset("manifest.webmanifest")),
        Route("/icon.svg", asset("icon.svg")),
        Route("/favicon.ico", asset("icon.svg")),
        Route("/api/watch", start, methods=["POST"]),
        Route("/api/watch/{job_id}", result, methods=["GET"]),
    ]
