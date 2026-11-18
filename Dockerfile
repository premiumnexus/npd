FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install -r requirements.txt

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/.store/media \
    && chown -R appuser:appuser /app/.store

COPY manage.py ./
COPY config/ ./config/
COPY development/ ./development/
COPY templates/ ./templates/
COPY static/ ./static/

USER appuser

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000", "--noreload"]
