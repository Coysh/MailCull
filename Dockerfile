FROM python:3.12-slim AS backend

WORKDIR /app

RUN addgroup --system mailcull && adduser --system --ingroup mailcull mailcull

COPY backend/pyproject.toml backend/requirements.txt* ./
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir -e . || true

COPY backend/ ./

FROM node:20-slim AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --frozen-lockfile 2>/dev/null || npm install

COPY frontend/ ./
RUN npm run build

FROM backend AS final

COPY --from=frontend-builder /frontend/dist /app/frontend/dist

RUN mkdir -p /data && chown mailcull:mailcull /data

USER mailcull

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${APP_PORT:-8420}/api/health')"

EXPOSE 8420

CMD ["python", "-m", "uvicorn", "mailcull.main:app", "--host", "0.0.0.0", "--port", "8420"]
