FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# curl is used by the container healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first so code edits do not reinstall them (chromadb is a large install).
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

# data/ and chroma_data/ are mounted as volumes; create them owned by the app user
# so a non-root process can seed sample data and write the vector store.
RUN useradd --create-home --uid 10001 dinebot \
    && mkdir -p /app/data /app/chroma_data \
    && chown -R dinebot:dinebot /app/data /app/chroma_data
USER dinebot

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
