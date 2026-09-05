FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Bot data (SQLite DB + logs) lives here; mount a volume so it survives redeploys.
ENV DATA_DIR=/app/data

# Install dependencies first so the layer cache survives code changes.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN mkdir -p /app/data && \
    useradd --create-home --uid 10001 appuser && \
    chown -R appuser:appuser /app

USER appuser

VOLUME /app/data

EXPOSE 8081

CMD ["python", "bot.py"]
