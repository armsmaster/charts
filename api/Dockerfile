# Base image is an ARG so the work PC can pull it through the internal Nexus
# Docker proxy, e.g.  --build-arg PYTHON_IMAGE=nexus.corp:8083/python:3.12-slim
ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}

# Nexus-proxied PyPI. Both default to empty, in which case public PyPI is used.
ARG PIP_INDEX_URL=""
ARG PIP_TRUSTED_HOST=""
# Debian mirror override for the same reason (optional).
ARG APT_MIRROR=""

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Kaleido's bundled headless renderer links against libnss3; everything else it
# needs is already in the slim image. Failure here is not fatal: the API falls
# back to browser-side PNG export and reports it via /api/meta/capabilities.
RUN set -eux; \
    if [ -n "$APT_MIRROR" ]; then \
      sed -i "s|http://deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
    fi; \
    (apt-get update && apt-get install -y --no-install-recommends libnss3 libexpat1 \
      && rm -rf /var/lib/apt/lists/*) || echo "WARN: apt unavailable, continuing without libnss3"

# Configure pip for the internal index before installing anything.
RUN set -eux; \
    if [ -n "$PIP_INDEX_URL" ]; then \
      printf '[global]\nindex-url = %s\n' "$PIP_INDEX_URL" > /etc/pip.conf; \
      if [ -n "$PIP_TRUSTED_HOST" ]; then \
        printf 'trusted-host = %s\n' "$PIP_TRUSTED_HOST" >> /etc/pip.conf; \
      fi; \
      cat /etc/pip.conf; \
    fi

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

RUN useradd --create-home --uid 10001 charts && chown -R charts:charts /app
USER charts

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"

CMD ["uvicorn", "moexcharts.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
