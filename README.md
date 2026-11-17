# ChatGPT Watch — YouTube → анализ в ChatGPT

**MVP v0.2: исходный код, сервер ещё не развёрнут.** MCP предоставляет инструменты start_watch и get_watch_result.

## Функции

- **Анализ речи и видеоряда:** Gemini Interactions API поддерживает прямой ввод публичной ссылки YouTube. Нужны GEMINI_API_KEY, доступ к модели и квоты Google API.
- **Без API-ключа:** попытка получить субтитры через youtube-transcript-api. Это НЕ просмотр кадров; субтитры могут отсутствовать.
- Принимаются только URL доменов YouTube. Доступ к MCP требует Bearer-токен.

## Запуск на компьютере/VPS (Python 3.12+)

Создай виртуальное окружение и установи зависимости:
    python -m venv .venv
    .venv/bin/pip install -r requirements.txt

Сгенерируй случайную строку для MCP_AUTH_TOKEN (минимум 24 символа) и задай её через переменную окружения, а не в коде.
При необходимости также задай GEMINI_API_KEY. Затем запусти:
    uvicorn watch.server:app --host 127.0.0.1 --port 8000

Проверка: GET http://127.0.0.1:8000/health
Защищённый MCP endpoint: POST http://127.0.0.1:8000/mcp
Тесты после установки pytest: PYTHONPATH=. pytest -q

## Docker

    docker build -t chatgpt-watch .
    docker run --rm -p 8000:8000 -e MCP_AUTH_TOKEN=YOUR_LONG_RANDOM_SECRET -e GEMINI_API_KEY=YOUR_KEY chatgpt-watch

## Подключение к ChatGPT

Потребуется постоянный публичный адрес HTTPS, например https://your-server.example/mcp, и возможность добавлять пользовательские MCP-серверы в твоём тарифе/клиенте. Инструкция ChatGPT: https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt

Обычный установленный навык ChatGPT Watch сам по себе сервер не запускает. На неподдерживаемых тарифах можно использовать отдельный MCP-клиент. Приложение iPhone не гарантирует поддержку настройки пользовательского MCP.

## Пример

1. start_watch(url="https://youtu.be/CK5sSoZYhJY", question="О чём говорится?", detail="balanced") возвращает job_id.
2. get_watch_result(job_id="...", wait_seconds=20) возвращает processing/completed/failed.
3. Режим captions_only означает только речь из доступных субтитров; video_and_audio — ответ модели по видео.

## Ограничения

- Не гарантируется анализ всех видео (приватные записи, блокировки, региональные ограничения, квоты).
- Результаты Gemini могут ошибаться; точные цитаты и таймкоды требуют сверки.
- Секреты не должны попадать в репозиторий. Не открывай /mcp без HTTPS и Bearer-авторизации.
- Используй только один процесс и одну реплику: задания временно хранятся в оперативной памяти, после рестарта теряются. Лимит — 4 одновременных задания.
- Сервер не использует cookies, не обходит DRM или ограничения приватности.
- Самостоятельная реализация, вдохновлённая https://github.com/bradautomates/claude-video.
