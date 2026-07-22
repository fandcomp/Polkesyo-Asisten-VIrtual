FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY tests ./tests
COPY entrypoint.sh ./

# Install Python dependencies
RUN pip install --no-cache-dir -e . && chmod +x entrypoint.sh

# Bake the multilingual embedding model into the image so startup loads it from the
# local cache instead of downloading at runtime (a fresh container previously stalled
# ~3 minutes downloading Chroma's ONNX model on the first chat request — same class of
# problem). Must match EMBEDDING_MODEL_NAME in .env; change both together.
ARG EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5)"

# entrypoint.sh waits for postgres, creates tables, then execs whatever CMD/command is given
# (dev's --reload default here, or prod's --workers override in docker-compose.prod.yml).
ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
