FROM python:3.12-slim AS backend

WORKDIR /app

RUN addgroup --system mailcull && adduser --system --ingroup mailcull --home /home/mailcull mailcull

COPY backend/pyproject.toml backend/requirements.txt* ./
COPY backend/mailcull ./mailcull
RUN pip install --no-cache-dir ".[browser]"

# Chromium + its system libraries for headless unsubscribe pages.
# Installed to a shared path so the non-root user can launch it.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN python -m playwright install --with-deps chromium \
    && chmod -R o+rx /opt/playwright

FROM node:20-slim AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM backend AS final

COPY --from=frontend-builder /frontend/dist /app/frontend/dist

RUN mkdir -p /data && chown mailcull:mailcull /data

USER mailcull

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8420/api/health')"

EXPOSE 8420

CMD ["python", "-m", "uvicorn", "mailcull.main:app", "--host", "0.0.0.0", "--port", "8420"]
