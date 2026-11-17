"""PWA routes and authorization contract; no external model/network needed."""
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.testclient import TestClient
from watch.web import WatchAuthMiddleware, web_routes

SECRET = "unit-test-secret-token-long-enough"

class FakeQueue:
    def start(self, url, question, detail):
        if url != "https://youtu.be/CK5sSoZYhJY":
            raise ValueError("Неправильная ссылка.")
        return {"job_id": "task-123", "status": "processing"}

    def start_text(self, transcript, question, detail):
        if len(transcript) < 30:
            raise ValueError("Текст короткий.")
        return {"job_id": "transcript-456", "status": "processing"}

    def result(self, job_id, wait_seconds):
        return {"job_id": job_id, "status": "completed",
                "result": {"mode": "captions_only", "captions": "[00:01] example"}}


def make_client(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", SECRET)
    return TestClient(Starlette(routes=web_routes(FakeQueue()),
                               middleware=[Middleware(WatchAuthMiddleware)]))


def test_public_pwa_serves_html_and_assets(monkeypatch):
    with make_client(monkeypatch) as client:
        index = client.get("/")
        assert index.status_code == 200
        assert "ChatGPT Watch" in index.text
        assert index.headers["content-type"].startswith("text/html")
        assert client.get("/app.js").status_code == 200
        assert client.get("/app.css").status_code == 200
        assert client.get("/manifest.webmanifest").json()["display"] == "standalone"
        assert client.get("/sw.js").status_code == 200


def test_private_watch_api_requires_token(monkeypatch):
    with make_client(monkeypatch) as client:
        assert client.post("/api/watch", json={"url": "https://youtu.be/CK5sSoZYhJY"}).status_code == 401
        assert client.get("/api/watch/task-123").status_code == 401
        bad = client.post("/api/watch", json={"url": "x"}, headers={"Authorization": "Bearer invalid"})
        assert bad.status_code == 401


def test_authorized_watch_roundtrip(monkeypatch):
    with make_client(monkeypatch) as client:
        headers = {"Authorization": f"Bearer {SECRET}"}
        response = client.post("/api/watch", headers=headers,
                               json={"url": "https://youtu.be/CK5sSoZYhJY", "detail": "balanced"})
        assert response.status_code == 202
        assert response.json()["job_id"] == "task-123"
        result = client.get("/api/watch/task-123", headers=headers)
        assert result.status_code == 200
        assert result.json()["status"] == "completed"
        assert result.headers["Cache-Control"] == "no-store"


def test_invalid_json_or_link(monkeypatch):
    with make_client(monkeypatch) as client:
        headers = {"Authorization": f"Bearer {SECRET}"}
        assert client.post("/api/watch", headers=headers, data="oops").status_code == 415
        assert client.post("/api/watch", headers=headers, json={"url": "bad"}).status_code == 400
        assert client.post("/api/watch", headers=headers, json=["not", "an", "object"]).status_code == 400



def test_user_transcript_api(monkeypatch):
    with make_client(monkeypatch) as client:
        payload = {"text": "В этом видео рассказывается об особенностях кумыкского языка.",
                   "detail": "balanced"}
        assert client.post("/api/transcript", json=payload).status_code == 401
        headers = {"Authorization": f"Bearer {SECRET}"}
        result = client.post("/api/transcript", headers=headers, json=payload)
        assert result.status_code == 202
        assert result.json()["job_id"] == "transcript-456"
        assert client.post("/api/transcript", headers=headers,
                           json={"text":"short"}).status_code == 400
