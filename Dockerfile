FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATABASE=/data/stopclop.db
WORKDIR /app
COPY requirements.txt .
RUN umask 022 && pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home app && mkdir -p /data && chown app:app /data
COPY server ./server
USER app
RUN python -c "import gunicorn.app.wsgiapp; from tempfile import TemporaryDirectory; from server.app import create_app; temporary = TemporaryDirectory(); app = create_app({'DATABASE': temporary.name + '/probe.db'}); assert app.test_client().get('/healthz').status_code == 200; temporary.cleanup()"
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--access-logfile", "-", "server.app:create_app()"]
