FROM python:3.15-slim-bookworm@sha256:4e03260adeeebafccd084f3584e6b84823aba5651cfb53ef8a078ed441ddf9cd

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --requirement /app/requirements.txt

COPY --chown=app:app alembic.ini /app/alembic.ini
COPY --chown=app:app migrations /app/migrations
COPY --chown=app:app app /app/app
# Keep the small authenticated MCP self-check in the runtime image so a
# deployment can verify its internal API without exposing a diagnostic port.
COPY --chown=app:app scripts/check_mcp.py /app/scripts/check_mcp.py

USER app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
