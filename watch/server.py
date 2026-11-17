"""Authenticated MCP HTTP server, exposing asynchronous video jobs."""
from __future__ import annotations
from contextlib import asynccontextmanager
import hmac
import os
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from .analyzers import analyze
from .core import WatchQueue

TOKEN = os.getenv("MCP_AUTH_TOKEN", "")
if len(TOKEN) < 24:
    raise RuntimeError("Set MCP_AUTH_TOKEN to a random string of at least 24 chars")
queue = WatchQueue(analyze)
mcp = FastMCP("ChatGPT Watch", stateless_http=True, json_response=True, host="0.0.0.0")

@mcp.tool()
def start_watch(url: str, question: str = "О чём говорится в видео?", detail: str = "balanced") -> dict:
    """Analyze a public YouTube video by URL. Returns a job ID; then call get_watch_result."""
    try:
        return queue.start(url=url, question=question, detail=detail)
    except ValueError as exc:
        return {"status": "invalid_input", "message": str(exc)}

@mcp.tool()
def get_watch_result(job_id: str, wait_seconds: float = 20) -> dict:
    """Fetch the actual analysis/transcript, waiting at most 25 seconds if processing."""
    try:
        return queue.result(job_id, wait_seconds=wait_seconds)
    except ValueError as exc:
        return {"status": "invalid_input", "message": str(exc)}

class BearerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health" and request.method == "GET":
            return await call_next(request)
        expected = "Bearer " + TOKEN
        if not hmac.compare_digest(request.headers.get("Authorization", ""), expected):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

async def health(request: Request) -> Response:
    return JSONResponse({"status": "ok", "service": "chatgpt-watch", "backend": "gemini" if os.getenv("GEMINI_API_KEY") else "captions_only"})

@asynccontextmanager
async def lifespan(app):
    async with mcp.session_manager.run():
        yield

app = Starlette(
    routes=[Route("/health", endpoint=health, methods=["GET"]), Mount("/", app=mcp.streamable_http_app())],
    middleware=[Middleware(BearerMiddleware)], lifespan=lifespan,
)
