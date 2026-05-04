FROM python:3.11-slim

WORKDIR /app

# Install Python deps (path relative to repo root build context)
COPY backend/pyproject.toml pyproject.toml

RUN pip install --no-cache-dir -e .

# Backend app code
COPY backend/app/ app/

# Pipeline source code — required at runtime for background ingestion tasks
COPY src/ src/

# Reference data (UNSPSC taxonomy, FX rates, keyword rules, savings rates)
COPY data/reference/ data/reference/

# Pipeline config
COPY config.yaml config.yaml

ENV PYTHONPATH=/app

EXPOSE 8000

# Pre-download sentence-transformers model to avoid cold-start delays
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
