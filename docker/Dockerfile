# prx-app image — Phase 1 FastAPI hello-world stub (P1.T7).
# The real app + full requirements arrive in Phase 6; kept minimal on purpose.
FROM python:3.11-slim

WORKDIR /app

# Stub deps only (fastapi + uvicorn). Phase 6 replaces this with the pinned app stack.
RUN pip install --no-cache-dir fastapi uvicorn

COPY docker/app_stub.py ./app_stub.py

EXPOSE 8000
CMD ["uvicorn", "app_stub:app", "--host", "0.0.0.0", "--port", "8000"]
