# prx-app image (P6.T10): build the React dashboard, then run the FastAPI app
# which serves both /api and the built dashboard at /. Phase 8 finalizes the
# runtime (health checks, volumes for data/ + the posterior, GHCR publish).

# --- Stage 1: build the dashboard ------------------------------------------
FROM node:24-slim AS dashboard
WORKDIR /dashboard
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci
COPY dashboard/ ./
RUN npm run build

# --- Stage 2: Python app ----------------------------------------------------
FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code (models import bambi lazily; the C/numba backend links on Linux).
COPY api/ ./api/
COPY models/ ./models/
COPY ingestion/ ./ingestion/
COPY scheduler/ ./scheduler/
COPY scripts/ ./scripts/

# Built dashboard from stage 1; DASHBOARD_DIST points the app at it.
COPY --from=dashboard /dashboard/dist ./dashboard/dist
ENV DASHBOARD_DIST=/app/dashboard/dist

# data/prx.db and models/saved/bayes_logistic.nc are provided at runtime via a
# volume mount (see docker-compose.yml) — not baked into the image.
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
