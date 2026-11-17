FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY watch ./watch
RUN useradd --create-home watch
USER watch
EXPOSE 8000
CMD ["uvicorn", "watch.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
