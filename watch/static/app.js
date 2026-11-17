"use strict";
(() => {
  const el = (id) => document.getElementById(id);
  const form = el("watch-form");
  const url = el("video-url");
  const secret = el("access-key");
  const question = el("question");
  const detail = el("detail");
  const panel = el("result-panel");
  const output = el("answer-text");
  const notice = el("message-panel");
  const progress = el("progress-panel");
  const action = el("analyze-btn");
  let running = false;
  let resultText = "";

  function inform(value, positive = false) {
    notice.textContent = value;
    notice.classList.remove("is-hidden");
    notice.classList.toggle("ok", positive);
  }
  function clearNotice() {
    notice.classList.add("is-hidden");
    notice.textContent = "";
  }
  function setBusy(value, label = "Получаем доступные материалы видео…") {
    running = value;
    action.disabled = value;
    el("btn-label").textContent = value ? "Идёт анализ…" : "Разобрать видео";
    el("progress-text").textContent = label;
    progress.classList.toggle("is-hidden", !value);
  }
  const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  async function api(path, options = {}) {
    let response;
    try {
      response = await fetch(path, {
        cache: "no-store",
        ...options,
        headers: { Authorization: "Bearer " + secret.value.trim(), ...(options.headers || {}) }
      });
    } catch (_) {
      throw new Error("Нет связи с сервером. Проверь интернет и адрес приложения.");
    }
    let data;
    try { data = await response.json(); }
    catch (_) { throw new Error("Сервер вернул неожиданный ответ."); }
    if (response.status === 401) throw new Error("Ключ доступа неверный. Проверь значение MCP_AUTH_TOKEN в настройках Render.");
    if (!response.ok) throw new Error(data.message || "Сервер не смог выполнить запрос.");
    return data;
  }

  function formatSeconds(time) {
    const parts = time.split(":").map(Number);
    if (parts.some((n) => !Number.isFinite(n))) return null;
    return parts.length === 3
      ? parts[0] * 3600 + parts[1] * 60 + parts[2]
      : parts[0] * 60 + parts[1];
  }

  function showText(value, source) {
    output.replaceChildren();
    const pattern = /(?<!\d)(?:\d{1,2}:)?\d{2}:\d{2}(?!\d)/g;
    let last = 0;
    for (const match of value.matchAll(pattern)) {
      output.append(document.createTextNode(value.slice(last, match.index)));
      const seconds = formatSeconds(match[0]);
      if (seconds !== null && source.startsWith("https://www.youtube.com/watch?v=")) {
        const link = document.createElement("a");
        link.className = "timestamp";
        link.textContent = match[0];
        link.href = source + "&t=" + seconds + "s";
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.title = "Открыть видео на этом моменте";
        output.append(link);
      } else {
        output.append(document.createTextNode(match[0]));
      }
      last = match.index + match[0].length;
    }
    output.append(document.createTextNode(value.slice(last)));
  }

  function displayResult(job) {
    const result = job.result || {};
    const captionsOnly = result.mode === "captions_only";
    resultText = captionsOnly ? (result.captions || "") : (result.analysis || "");
    if (!resultText) throw new Error("В ответе нет текста. Попробуй другое видео.");
    el("result-badge").textContent = captionsOnly ? "ТОЛЬКО СУБТИТРЫ" : "ВИДЕО + АУДИО";
    el("result-badge").classList.toggle("captions", captionsOnly);
    el("result-disclaimer").textContent = captionsOnly
      ? "Получены только доступные субтитры. Это не полноценный пересказ и кадры не анализировались. Настрой GEMINI_API_KEY для видеоанализа." + (result.truncated ? " Субтитры обрезаны по лимиту." : "")
      : "Разбор сделан моделью AI. Проверяй важные цитаты и утверждения по оригиналу.";
    const source = result.source || "";
    showText(resultText, source);
    const sourceLink = el("source-link");
    sourceLink.hidden = !source.startsWith("https://www.youtube.com/watch?v=");
    if (!sourceLink.hidden) sourceLink.href = source;
    panel.classList.remove("is-hidden");
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (running) return;
    clearNotice();
    panel.classList.add("is-hidden");
    if (!url.value.trim()) { inform("Вставь ссылку на YouTube."); url.focus(); return; }
    if (secret.value.trim().length < 24) {
      inform("Введи секретный ключ из настроек сервера (не короче 24 символов).");
      secret.focus();
      return;
    }
    setBusy(true, "Запускаем анализ…");
    try {
      const start = await api("/api/watch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: url.value.trim(),
          question: question.value.trim() || "О чём говорится в видео?",
          detail: detail.value
        })
      });
      if (!start.job_id) throw new Error(start.message || "Не получилось создать задачу.");
      let completed = false;
      for (let attempt = 0; attempt < 120; attempt++) {
        const data = await api("/api/watch/" + encodeURIComponent(start.job_id));
        if (data.status === "completed") {
          displayResult(data);
          completed = true;
          break;
        }
        if (data.status === "failed" || data.status === "not_found") {
          throw new Error(data.message || "Не удалось обработать ролик. Проверь доступность видео, Gemini API и квоты.");
        }
        if (attempt === 5) el("progress-text").textContent = "Обрабатывается видео. Длинным роликам может потребоваться больше времени…";
        await pause(2500);
      }
      if (!completed) inform("Анализ ещё не завершён. Можно повторить запрос — сервер временно хранит задачи.");
    } catch (error) {
      inform(error.message || "Неизвестная ошибка.");
    } finally {
      setBusy(false);
    }
  });

  el("paste-btn").addEventListener("click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        url.value = text.trim();
        url.focus();
        clearNotice();
      } else inform("Буфер обмена пуст.");
    } catch (_) {
      inform("Браузер не разрешил чтение буфера. Нажми и удерживай поле ссылки, затем выбери «Вставить».");
    }
  });
  el("toggle-key").addEventListener("click", () => {
    const revealed = secret.type === "password";
    secret.type = revealed ? "text" : "password";
    const button = el("toggle-key");
    button.textContent = revealed ? "Скрыть" : "Показать";
    button.setAttribute("aria-pressed", String(revealed));
    button.setAttribute("aria-label", revealed ? "Скрыть ключ доступа" : "Показать ключ доступа");
  });
  el("copy-btn").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(resultText);
      inform("Разбор скопирован.", true);
    } catch (_) {
      inform("Не удалось скопировать автоматически. Выдели текст вручную.");
    }
  });
  el("download-btn").addEventListener("click", () => {
    if (!resultText) return;
    const blob = new Blob([resultText], { type: "text/plain;charset=utf-8" });
    const objectURL = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectURL;
    a.download = "chatgpt-watch-result.txt";
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(objectURL), 3000);
  });

  fetch("/health", { cache: "no-store" }).then((response) => {
    if (!response.ok) throw new Error("server offline");
    return response.json();
  }).then((data) => {
    const status = el("server-status");
    status.classList.add("ready");
    status.querySelector("span").textContent = data.backend === "gemini"
      ? "Видеоанализ доступен" : "Режим субтитров";
  }).catch(() => {
    const status = el("server-status");
    status.classList.add("error");
    status.querySelector("span").textContent = "Сервер не отвечает";
  });

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    });
  }
})();
