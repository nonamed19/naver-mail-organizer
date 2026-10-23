FROM python:3.12-slim

WORKDIR /app

COPY server.py probe.py /app/

RUN chmod 755 /app \
    && chmod 644 /app/server.py /app/probe.py \
    && useradd --uid 10001 --create-home mailbridge \
    && mkdir /data \
    && chown mailbridge /data

USER mailbridge

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MCP_BIND=0.0.0.0 \
    PORT=8080 \
    NAVER_AUDIT_DB=/data/audit.sqlite3

EXPOSE 8080

CMD ["python", "server.py"]