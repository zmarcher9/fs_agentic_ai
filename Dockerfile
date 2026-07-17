FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.lock .
# Corporate SSL interception often lacks a private CA inside the build
# container. Trust PyPI hosts for package install only; runtime still uses
# the image CA store for app HTTPS.
RUN python -m pip install --no-cache-dir \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    --trusted-host pypi.python.org \
    -r requirements.lock

COPY --chown=pwuser:pwuser . .

USER pwuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

# One worker is mandatory while browser sessions, agent memory, rate limits,
# auth tokens, and caches remain process-local.
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
