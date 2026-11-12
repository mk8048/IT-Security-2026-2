FROM python:3.13-slim-bookworm@sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY services/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home app \
    && mkdir /data /files && chown app:app /data /files
COPY services/*.py ./
COPY services/templates ./templates
USER 10001:10001
CMD ["gunicorn", "--bind=0.0.0.0:8000", "--workers=2", "--timeout=20", "--no-control-socket", "--forwarded-allow-ips=", "app:app"]
