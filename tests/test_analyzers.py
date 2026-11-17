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
    assert 'НЕ анализировалось' in result['verification']
