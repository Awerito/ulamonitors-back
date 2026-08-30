# Builder
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /install
COPY requirements.txt .
RUN uv venv /opt/venv && VIRTUAL_ENV=/opt/venv uv pip install -r requirements.txt

# Final — no build tools in the runtime image
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=America/Santiago
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY . /app
EXPOSE 8000
# Shell form so the same image honours Cloud Run's $PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
