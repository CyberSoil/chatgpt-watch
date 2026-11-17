import sys
from types import ModuleType, SimpleNamespace
from watch.analyzers import analyze

def test_gemini_interactions_receives_canonical_youtube_url(monkeypatch):
    calls = []
    class Client:
        def __init__(self, api_key):
            assert api_key == 'fake-key'
            self.interactions = SimpleNamespace(create=self.create)
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_text='Проверенный результат тестовой модели')
    google = ModuleType('google')
    google.genai = SimpleNamespace(Client=Client)
    monkeypatch.setitem(sys.modules, 'google', google)
    monkeypatch.setenv('GEMINI_API_KEY', 'fake-key')
    answer = analyze('https://youtu.be/CK5sSoZYhJY?t=4', 'CK5sSoZYhJY', 'О чём?', 'balanced')
    assert answer['mode'] == 'video_and_audio'
    assert calls[0]['input'][1]['uri'] == 'https://www.youtube.com/watch?v=CK5sSoZYhJY'
    assert 'Проверенный' in answer['analysis']

def test_caption_fallback_is_clearly_text_only(monkeypatch):
    class YoutubeTranscriptApi:
        def fetch(self, video_id, languages):
            assert video_id == 'CK5sSoZYhJY'
            return [SimpleNamespace(text='hello world', start=5), SimpleNamespace(text='goodbye', start=62)]
    module = ModuleType('youtube_transcript_api')
    module.YouTubeTranscriptApi = YoutubeTranscriptApi
    monkeypatch.setitem(sys.modules, 'youtube_transcript_api', module)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    result = analyze('https://youtu.be/CK5sSoZYhJY', 'CK5sSoZYhJY', 'О чём?', 'balanced')
    assert result['mode'] == 'captions_only'
    assert '[00:05] hello world' in result['captions']
    assert '[01:02] goodbye' in result['captions']
    assert 'НЕ анализировались' in result['verification']



def test_vtt_parser_preserves_timestamps():
    from watch.analyzers import _parse_vtt
    text = ("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello world\n\n"
            "00:00:03.000 --> 00:00:05.000\nHello world\n\n"
            "00:00:06.000 --> 00:00:08.000\nNext phrase\n")
    result = _parse_vtt(text)
    assert "[00:00:01] Hello world" in result
    assert "[00:00:06] Next phrase" in result
    assert result.count("Hello world") == 1


def test_manual_transcript_needs_no_google_and_labels_source(monkeypatch):
    from watch.analyzers import analyze_transcript
    for key in ("GEMINI_API_KEY", "YANDEX_API_KEY", "YANDEX_FOLDER_ID",
                "TEXT_AI_API_KEY", "TEXT_AI_MODEL", "TEXT_AI_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    result = analyze_transcript("[00:01] Привет! Сегодня обсудим северные языки Кавказа.", "О чём?", "balanced")
    assert result["mode"] == "captions_only"
    assert result["engine"] == "user_transcript"
    assert "НЕ анализировались" in result["verification"]
    assert "analysis" not in result


def test_yandex_provider_analyzes_only_text(monkeypatch):
    from watch import providers
    monkeypatch.setenv("YANDEX_API_KEY", "dummy-dont-use")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "testfolder123")
    calls = []
    def fake_post(url, headers, payload):
        calls.append((url, headers, payload))
        return {"output": [{"content": [{"type": "output_text", "text": "Это обзор темы."}]}]}
    monkeypatch.setattr(providers, "_post_json", fake_post)
    summary, engine = providers.summarize_text("Обсуждаем язык, проблемы и традиции.", "Что важно?", "brief")
    assert engine == "yandex"
    assert summary == "Это обзор темы."
    assert calls[0][0] == "https://ai.api.cloud.yandex.net/v1/responses"
    assert calls[0][2]["model"] == "gpt://testfolder123/yandexgpt-5.1"


def test_provider_url_rejects_private_hosts():
    from watch.providers import _safe_compatible_endpoint, AIProviderError
    for bad in ("http://example.com/v1", "https://localhost/v1",
                "https://127.0.0.1/v1", "https://user:secret@example.com/v1"):
        try:
            _safe_compatible_endpoint(bad)
        except AIProviderError:
            pass
        else:
            raise AssertionError("Unsafe endpoint accepted: " + bad)
    assert _safe_compatible_endpoint("https://api.example.com/v1") == "https://api.example.com/v1/chat/completions"
