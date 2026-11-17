"""Pure input validation and job orchestration, independent of MCP and Gemini."""
from __future__ import annotations
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
import logging
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

log = logging.getLogger("watch")



def classify_processing_error(exc: Exception) -> tuple[str, str]:
    """Return a safe, actionable error code and a message (never echo raw exceptions)."""
    name = type(exc).__name__
    youtube_errors = {
        "RequestBlocked": ("youtube_blocked", "YouTube отклонил запрос с адреса сервера. Это часто происходит на облачных хостингах. Для видеоанализа подключи GEMINI_API_KEY в Render."),
        "IpBlocked": ("youtube_blocked", "YouTube временно заблокировал IP-адрес сервера. Режим субтитров здесь недоступен. Подключи GEMINI_API_KEY для анализа роликов."),
        "NoTranscriptFound": ("no_requested_captions", "Для этого видео нет доступных субтитров на русском или английском. Можно попробовать другое видео либо анализ через Gemini."),
        "TranscriptsDisabled": ("captions_disabled", "Субтитры у этого видео отключены. Для анализа содержимого нужен Gemini API."),
        "VideoUnavailable": ("video_unavailable", "YouTube сообщает, что видео недоступно. Проверь ссылку и доступ к ролику."),
        "VideoUnplayable": ("video_unavailable", "Воспроизведение этого видео недоступно сервису."),
        "AgeRestricted": ("age_restricted", "Видео имеет возрастное ограничение, которое этот сервер не может обойти."),
        "PoTokenRequired": ("youtube_token_required", "YouTube требует дополнительную проверку для получения субтитров. Подключи Gemini для видеоанализа."),
        "YouTubeRequestFailed": ("youtube_request_failed", "Ошибка запроса к YouTube. Возможны сетевые ограничения, блокировка IP или временная недоступность."),
        "FailedToCreateConsentCookie": ("youtube_consent", "YouTube не разрешил получить субтитры с этого сервера."),
        "YouTubeDataUnparsable": ("youtube_changed", "Ответ YouTube не удалось разобрать. Возможно, изменился формат данных."),
    }
    if name in youtube_errors:
        return youtube_errors[name]
    if name == "CaptionsUnavailable":
        return "captions_unavailable", "YouTube отклонил запрос нашего сервера. Для автоматического получения субтитров можно настроить SUPADATA_API_KEY в Render (отдельный внешний сервис). Либо переключись на «Расшифровка или файл» и загрузи .srt, .vtt или .txt."
    if name == "HostedCaptionsError":
        reason = getattr(exc, "reason", "")
        explanations = {
            "auth": "Сервис Supadata отклонил API-ключ. Проверь SUPADATA_API_KEY в Render.",
            "quota": "У Supadata закончились кредиты или достигнут лимит запросов. Проверь баланс и тариф.",
            "timeout": "Supadata не успел обработать видео. Попробуй более короткий ролик или вставь расшифровку.",
            "no_captions": "Supadata не нашёл субтитры у этого ролика. Попробуй режим auto/generate в SUPADATA_MODE, учитывая расход кредитов.",
            "invalid_mode": "В Render для SUPADATA_MODE выбери native, auto или generate.",
        }
        return "supadata_" + (reason if reason in explanations else "unavailable"), explanations.get(
            reason, "Supadata не смог получить субтитры. Проверь ссылку, тариф и настройки провайдера."
        )
    if name == "AIProviderError":
        return "text_ai_error", "Сервис анализа текста не ответил. Проверь ключ, модель, квоты и настройки текстового AI-провайдера в Render."
    status = getattr(exc, "code", None)
    if isinstance(status, int):
        if status in (401, 403):
            return "gemini_auth", "Google отклонил запрос к Gemini. Проверь GEMINI_API_KEY и доступ к модели в Google AI Studio."
        if status == 429:
            return "gemini_quota", "Gemini сообщил о превышении квоты. Проверь лимиты и оплату API в Google AI Studio."
        if status == 404:
            return "gemini_model", "Модель Gemini недоступна для этого ключа. Проверь GEMINI_MODEL в Render."
        if status in (400, 422):
            return "gemini_input", "Gemini не принял параметры или ссылку видео. Проверь доступность ролика и модель."
    if name in ("TimeoutError", "ReadTimeout", "ConnectTimeout"):
        return "timeout", "Сервис видеоанализа не ответил вовремя. Попробуй ещё раз."
    return "processing_failed", "Не удалось обработать видео. Проверь субтитры, настройки Gemini и журналы сервера Render."


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
                    if job.future.done() and job.future.exception() is not None:
                        continue  # allow retry after a temporary failure or new API config
                    return {"job_id": job.id, "status": "completed" if job.future.done() else "processing", "reused": True}
            if sum(not j.future.done() for j in self.jobs.values()) >= self.max_jobs:
                return {"status": "busy", "message": "Сервер занят: повтори попытку позже."}
            job_id = secrets.token_urlsafe(18)
            future = self.executor.submit(self.analyzer, canonical, video_id, question, detail)
            self.jobs[job_id] = Job(job_id, monotonic(), future, key)
        return {"job_id": job_id, "status": "processing", "reused": False}

    def start_text(self, transcript: str, question: str = "О чём говорится в видео?", detail: str = "balanced") -> dict:
        """Analyze transcript supplied by the user without contacting YouTube."""
        if not isinstance(transcript, str) or not 30 <= len(transcript.strip()) <= 90000:
            raise ValueError("Введи текст от 30 до 90 000 символов.")
        if detail not in DETAILS:
            raise ValueError("detail: brief, balanced или detailed")
        question = (question or "О чём говорится в видео?").strip()
        if len(question) > 1500:
            raise ValueError("Вопрос слишком длинный (максимум 1500 символов).")
        text = transcript.strip()
        from .analyzers import analyze_transcript
        key = sha256(("transcript\\0" + text + "\\0" + question + "\\0" + detail).encode()).hexdigest()
        with self.lock:
            self._prune()
            for job in self.jobs.values():
                if job.fingerprint == key and (not job.future.done() or job.future.exception() is None):
                    return {"job_id": job.id,
                            "status": "completed" if job.future.done() else "processing",
                            "reused": True}
            if sum(not j.future.done() for j in self.jobs.values()) >= self.max_jobs:
                return {"status": "busy", "message": "Сервер занят: повтори попытку позже."}
            job_id = secrets.token_urlsafe(18)
            future = self.executor.submit(analyze_transcript, text, question, detail)
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
            code, message = classify_processing_error(exc)
            status_code = getattr(exc, "code", None)
            safe_status = status_code if isinstance(status_code, int) and 400 <= status_code <= 599 else None
            log.warning("watch_job_failed type=%s reason=%s http_status=%s",
                        type(exc).__name__, code, safe_status)
            return {"status": "failed", "job_id": job_id, "error": code, "message": message}
        return {"status": "completed", "job_id": job_id, "result": result}
