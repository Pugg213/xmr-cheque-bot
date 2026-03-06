FROM python:3.12-slim-bookworm

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy project metadata + sources (needed for editable install)
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install the package (editable)
RUN pip install --no-cache-dir -e .

# Run as non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

CMD ["python", "-m", "xmr_cheque_bot"]