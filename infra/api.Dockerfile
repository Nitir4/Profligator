FROM python:3.12-slim-bookworm
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.22
COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/
RUN uv sync --project apps/api --frozen --no-dev --no-managed-python
RUN useradd --uid 10001 --create-home profligator
COPY --chown=profligator:profligator apps/api/src apps/api/src
COPY --chown=profligator:profligator apps/api/alembic apps/api/alembic
COPY --chown=profligator:profligator apps/api/alembic.ini apps/api/alembic.ini
COPY --chown=profligator:profligator scripts/run_scheduler.py scripts/run_scheduler.py
ENV PATH="/app/apps/api/.venv/bin:$PATH" PYTHONPATH="/app/apps/api/src" PYTHONUNBUFFERED=1
USER profligator
EXPOSE 8000
CMD ["uvicorn", "profligator_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
