# ChatGPT Watch 0.4 — независимый анализ YouTube и субтитров на iPhone

[Deploy to Render](https://render.com/deploy?repo=https://github.com/CyberSoil/chatgpt-watch)

Это отдельное PWA, а не встроенная функция ChatGPT. Уже созданный сервис: https://chatgpt-watch-ctww.onrender.com

## Возможности

- YouTube URL: сначала youtube-transcript-api, затем yt-dlp пробуют получить субтитры без скачивания видео и аудиодорожки.
- Ручной ввод: текст стенограммы от 30 до 90 000 символов, либо импорт TXT / SRT / VTT с iPhone (до 100 КБ).
- При наличии ключей Yandex AI Studio — смысловой пересказ текста на русском; используемые переменные YANDEX_API_KEY, YANDEX_FOLDER_ID и необязательная YANDEX_MODEL (по умолчанию yandexgpt-5.1).
- Альтернативно поддерживается совместимый Chat Completions API: TEXT_AI_API_KEY, TEXT_AI_MODEL, TEXT_AI_BASE_URL (HTTPS base URL с /v1, без /chat/completions).
- Gemini — необязательный модуль анализа кадров и аудио публичного видео при разрешённом доступе и наличии GEMINI_API_KEY.
- Без AI-провайдера программа показывает исходный текст, НЕ выдавая его за содержательный пересказ. Без видео-модели кадры НЕ анализируются.
- Возможность копировать результат, сохранять TXT и просматривать оригинальные субтитры. Ссылка и таймкоды кликабельны, если присутствуют.

## Настройка существующего сервера Render

Открой https://dashboard.render.com/web/srv-dbtupgbm8hqs73dk8org → Environment.

1. Смените ранее показанный на скриншоте MCP_AUTH_TOKEN, создайте новый случайный секрет длиннее 24 символов и сохраните его приватно. Он вводится в форму Watch, но не в GitHub.
2. Для реального AI-пересказа по тексту можно подключить Yandex AI Studio: создайте сервисный API-ключ и найдите ID каталога в Yandex Cloud. Документация: https://aistudio.yandex.ru/ru/docs/ai-studio/operations/generation/create-prompt
3. Установите YANDEX_API_KEY и YANDEX_FOLDER_ID как приватные переменные окружения сервиса. Опционально YANDEX_MODEL=yandexgpt-5.1. Использование модели может тарифицироваться; проверьте квоты.
4. Или используйте другого официально доступного текстового провайдера с OpenAI-compatible Chat Completions API через TEXT_AI_API_KEY, TEXT_AI_MODEL, TEXT_AI_BASE_URL.
5. Выбери Save, rebuild, and deploy. Открой https://chatgpt-watch-ctww.onrender.com в Safari и выбери источник «YouTube» или «Расшифровка/файл».

**Никаких ключей и паролей в GitHub, screenshots, чат или browser code.** Gemini не обязателен. PWA не сохраняет секрет в localStorage/cookies, но текст расшифровки отправляется на личный сервер и, при выборе AI, соответствующему провайдеру.

## Источники и честные ограничения

Обработка по одной ссылке зависит от доступности субтитров YouTube. yt-dlp — запасной парсер, а не гарантированный обход IP-блокировок. Если оба адаптера недоступны, понадобится вручную вставить или загрузить стенограмму. Видео, звук и кадры в ручном режиме не анализируются. Для автоматического распознавания аудио/кадров потребуется дополнительный легальный источник медиа и ASR/Vision-модуль; эта часть пока не реализована. Google Gemini может анализировать кадры, если его API настроен и доступен.

Длинные видео и ASR пока не гарантированы. На Render Free сервер может засыпать, задания хранятся в памяти одного процесса и удаляются после рестарта; текст живёт в памяти до очистки задания (примерно один час). Максимум четыре параллельные задачи.

## Локальный запуск и тестирование

Нужен Python 3.12+. Установи зависимости: pip install -r requirements.txt

Задай MCP_AUTH_TOKEN (24+ символа), а ключи AI-провайдера — только если они нужны. Запуск: uvicorn watch.server:app --host 127.0.0.1 --port 8000

Тесты: pip install pytest httpx && python -m pytest -q

API: POST /api/watch (url, question, detail); POST /api/transcript (text, question, detail); GET /api/watch/{job_id} (статус и результат); GET /health (публичный статус). Защита: Authorization: Bearer <MCP_AUTH_TOKEN>. MCP инструменты: start_watch, analyze_pasted_transcript, get_watch_result.

Самостоятельная реализация по мотивам https://github.com/bradautomates/claude-video.
