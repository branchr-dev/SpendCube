FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml pyproject.toml

RUN pip install --no-cache-dir -e .

COPY app/ app/

ENV PYTHONPATH=/app

EXPOSE 8000

# Pre-download sentence-transformers model to avoid cold-start delays
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# src/ and data/ are mounted as volumes at runtime via docker-compose; not COPY'd into the image
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
