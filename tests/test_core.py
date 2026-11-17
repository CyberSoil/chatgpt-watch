import pytest
from watch.core import normalize_youtube_url, InvalidVideoURL, WatchQueue

@pytest.mark.parametrize("url", [
    "https://youtu.be/CK5sSoZYhJY?si=abcd",
    "https://www.youtube.com/watch?v=CK5sSoZYhJY&t=50",
    "https://m.youtube.com/watch?v=CK5sSoZYhJY",
    "https://www.youtube.com/shorts/CK5sSoZYhJY",
    "https://www.youtube.com/live/CK5sSoZYhJY",
])
def test_valid_links(url):
    assert normalize_youtube_url(url) == ("https://www.youtube.com/watch?v=CK5sSoZYhJY", "CK5sSoZYhJY")

@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "https://youtube.com.evil.org/watch?v=CK5sSoZYhJY",
    "https://127.0.0.1/watch?v=CK5sSoZYhJY", "https://www.youtube.com/watch?v=wrong",
    "https://www.youtube.com/watch?v=CK5sSoZYhJY&v=AAAAAAAAAAA",
    "https://user:pass@youtube.com/watch?v=CK5sSoZYhJY",
    "http://youtube.com:1234/watch?v=CK5sSoZYhJY",
])
def test_rejects_other_urls(url):
    with pytest.raises(InvalidVideoURL):
        normalize_youtube_url(url)

def test_jobs_and_dedup():
    q = WatchQueue(lambda url, video_id, question, detail: {"mode":"stub", "id":video_id})
    a = q.start("https://youtu.be/CK5sSoZYhJY")
    b = q.start("https://youtu.be/CK5sSoZYhJY")
    assert a["job_id"] == b["job_id"]
    assert b["reused"] is True
    assert q.result(a["job_id"], 3)["result"]["id"] == "CK5sSoZYhJY"
    assert q.result("missing")["status"] == "not_found"

def test_error_does_not_expose_exception():
    def failing(*args):
        raise RuntimeError("secret-key-123")
    q = WatchQueue(failing)
    job_id = q.start("https://youtu.be/CK5sSoZYhJY")["job_id"]
    response = q.result(job_id, 2)
    assert response["status"] == "failed"
    assert "secret-key-123" not in str(response)


def test_failed_jobs_can_be_retried():
    calls = {"count": 0}
    def analyzer(*args):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("transient")
        return {"ok": True}
    q = WatchQueue(analyzer)
    first = q.start("https://youtu.be/CK5sSoZYhJY")
    assert q.result(first["job_id"], 5)["status"] == "failed"
    second = q.start("https://youtu.be/CK5sSoZYhJY")
    assert second["job_id"] != first["job_id"]
    assert q.result(second["job_id"], 5)["status"] == "completed"


def test_user_friendly_error_types():
    from watch.core import classify_processing_error

    RequestBlocked = type("RequestBlocked", (Exception,), {})
    error, message = classify_processing_error(RequestBlocked("sensitive data!"))
    assert error == "youtube_blocked"
    assert "sensitive data" not in message
    assert "Gemini" in message

    ApiError = type("ClientError", (Exception,), {})
    exc = ApiError("secret API key")
    exc.code = 429
    error, message = classify_processing_error(exc)
    assert error == "gemini_quota"
    assert "secret API key" not in message

    exc.code = 401
    error, message = classify_processing_error(exc)
    assert error == "gemini_auth"
    assert "GEMINI_API_KEY" in message
