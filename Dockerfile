# Pin the multi-platform index so native amd64 and arm64 builds use the same release.
FROM python:3.13.16-alpine3.24@sha256:2d9aefe2fef018a7eb2c13064c89c71929800fd2e5dccdbf52ea5da5bb8d929a
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATABASE=/data/stopclop.db
WORKDIR /app
COPY requirements.txt .
# The pinned base predates Alpine's CVE-2026-85091 fix; require the patched zlib.
# Installation tools and their vendored dependencies are not needed at runtime.
RUN umask 022 \
    && apk add --no-cache --upgrade "zlib>=1.3.2-r1" \
    && python -m pip install --no-cache-dir --only-binary=:all: -r requirements.txt \
    && python -m pip uninstall -y pip \
    && rm -rf /usr/local/lib/python3.13/ensurepip \
    && addgroup -g 10001 app \
    && adduser -D -u 10001 -G app app \
    && mkdir -p /data && chown app:app /data
COPY server ./server
USER app
RUN python -c "import gunicorn.app.wsgiapp; from tempfile import TemporaryDirectory; from server.app import create_app; temporary = TemporaryDirectory(); app = create_app({'DATABASE': temporary.name + '/probe.db'}); assert app.test_client().get('/healthz').status_code == 200; temporary.cleanup()"
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "32", "--timeout", "120", "--access-logfile", "-", "server.app:create_app()"]
