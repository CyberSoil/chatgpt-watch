"""Combined Watch PWA, REST queue API and authenticated MCP server."""
from __future__ import annotations
from contextlib import asynccontextmanager
import os

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.middleware import Middleware

from .analyzers import analyze
from .core import WatchQueue
from .web import WatchAuthMiddleware, web_routes

if len(os.getenv("MCP_AUTH_TOKEN", "")) < 24:
    raise RuntimeError("Set MCP_AUTH_TOKEN to a random string of at least 24 chars")

queue = WatchQueue(analyze)
mcp = FastMCP("ChatGPT Watch", stateless_http=True, json_response=True, host="0.0.0.0")


@mcp.tool()
def start_watch(url: str, question: str = "О чём говорится в видео?", detail: str = "balanced") -> dict:
    """Analyze a public YouTube video by URL. Returns job_id."""
    try:
        return queue.start(url=url, question=question, detail=detail)
    except ValueError as exc:
        return {"status": "invalid_input", "message": str(exc)}


@mcp.tool()
def get_watch_result(job_id: str, wait_seconds: float = 20) -> dict:
    """Fetch video analysis or captions by job ID, waiting up to 25 seconds."""
    try:
        return queue.result(job_id, wait_seconds=wait_seconds)
    except ValueError as exc:
        return {"status": "invalid_input", "message": str(exc)}


async def health(request) -> Response:
    return JSONResponse({"status": "ok", "service": "chatgpt-watch",
                         "backend": "gemini" if os.getenv("GEMINI_API_KEY") else "captions_only"})


@asynccontextmanager
async def lifespan(app):
    async with mcp.session_manager.run():
        yield


app = Starlette(
    routes=[Route("/health", endpoint=health, methods=["GET"]),
            *web_routes(queue), Mount("/", app=mcp.streamable_http_app())],
    middleware=[Middleware(WatchAuthMiddleware)],
    lifespan=lifespan,
)
