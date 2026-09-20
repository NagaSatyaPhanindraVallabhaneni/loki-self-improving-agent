FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY loki/ ./loki/
COPY examples/ ./examples/

ENV PYTHONPATH=/app

# Show usage; run with: docker run -e LOKI_API_KEY=... loki "your task here"
CMD ["python", "-m", "loki", "--help"]
