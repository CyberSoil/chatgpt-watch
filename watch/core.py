"""Pure input validation and job orchestration, independent of MCP and Gemini."""
from __future__ import annotations
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from hashlib import sha256
from threading import RLock
from time import monotonic
from urllib.parse import parse_qs, urlparse
import re
import secrets

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com"}
DETAILS = {"brief", "balanced", "detailed"}

class InvalidVideoURL(ValueError):
    pass

def normalize_youtube_url(url: str) -> tuple[str, str]:
    """Return canonical public YouTube URL and video ID; reject arbitrary hosts/SSRF."""
    if not isinstance(url, str) or len(url) > 2048:
        raise InvalidVideoURL("Нужна короткая публичная ссылка YouTube.")
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in ("https", "http") or host not in HOSTS or parsed.username or parsed.password or parsed.port not in (None, 80, 443):
        raise InvalidVideoURL("Поддерживаются только публичные ссылки youtube.com и youtu.be.")
    parts = [x for x in parsed.path.split("/") if x]
    if host.endswith("youtu.be"):
        video_id = parts[0] if len(parts) == 1 else ""
    elif parts and parts[0] == "watch":
        values = parse_qs(parsed.query).get("v", [])
        video_id = values[0] if len(values) == 1 else ""
    elif len(parts) == 2 and parts[0] in ("shorts", "live", "embed", "v"):
        video_id = parts[1]
    else:
        video_id = ""
    if not VIDEO_ID.fullmatch(video_id):
        raise InvalidVideoURL("Не удалось извлечь ID видео YouTube из ссылки.")
    return f"https://www.youtube.com/watch?v={video_id}", video_id

@dataclass
class Job:
    id: str
    created: float
    future: Future
    fingerprint: str

class WatchQueue:
    """Bounded in-memory queue; deploy one process/replica for this reference MVP."""
    def __init__(self, analyzer, max_jobs: int = 4, retention_seconds: int = 3600):
        self.analyzer = analyzer
        self.max_jobs = max_jobs
        self.retention = retention_seconds
        self.executor = ThreadPoolExecutor(max_workers=max_jobs, thread_name_prefix="watch")
        self.jobs: dict[str, Job] = {}
        self.lock = RLock()

    def _prune(self):
        now = monotonic()
        self.jobs = {k: v for k, v in self.jobs.items() if now - v.created < self.retention or not v.future.done()}

    def start(self, url: str, question: str = "О чём говорится в видео?", detail: str = "balanced") -> dict:
        canonical, video_id = normalize_youtube_url(url)
        if detail not in DETAILS:
            raise ValueError("detail: brief, balanced или detailed")
        question = (question or "О чём говорится в видео?").strip()
        if len(question) > 1500:
            raise ValueError("Вопрос слишком длинный (максимум 1500 символов).")
        key = sha256(f"{video_id}\0{question}\0{detail}".encode()).hexdigest()
        with self.lock:
            self._prune()
            for job in self.jobs.values():
                if job.fingerprint == key:
                    return {"job_id": job.id, "status": "completed" if job.future.done() and job.future.exception() is None else ("failed" if job.future.done() else "processing"), "reused": True}
            if sum(not j.future.done() for j in self.jobs.values()) >= self.max_jobs:
                return {"status": "busy", "message": "Сервер занят: повтори попытку позже."}
            job_id = secrets.token_urlsafe(18)
            future = self.executor.submit(self.analyzer, canonical, video_id, question, detail)
            self.jobs[job_id] = Job(job_id, monotonic(), future, key)
        return {"job_id": job_id, "status": "processing", "reused": False}

    def result(self, job_id: str, wait_seconds: float = 0) -> dict:
        if not isinstance(job_id, str) or len(job_id) > 128:
            return {"status": "not_found"}
        with self.lock:
            self._prune()
            job = self.jobs.get(job_id)
        if job is None:
            return {"status": "not_found", "message": "Задание не найдено или срок хранения истёк."}
        if wait_seconds < 0 or wait_seconds > 25:
            raise ValueError("wait_seconds должен быть от 0 до 25")
        try:
            result = job.future.result(timeout=wait_seconds)
        except TimeoutError:
            return {"status": "processing", "job_id": job_id}
        except Exception as exc:
            return {"status": "failed", "job_id": job_id, "error": type(exc).__name__, "message": "Не удалось проанализировать видео. Проверь доступность ссылки и настройки сервера."}
        return {"status": "completed", "job_id": job_id, "result": result}
