FROM python:3.12-slim AS base

WORKDIR /app

# Install system deps + Node.js (for MCP stdio servers) + Azure CLI (for MCP auth)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl gnupg \
    libpango1.0-dev libgdk-pixbuf-2.0-dev libffi-dev shared-mime-info && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    curl -sL https://aka.ms/InstallAzureCLIDeb | bash && \
    rm -rf /var/lib/apt/lists/*

# Copy dependency spec and install
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir -e ".[full]" 2>/dev/null || pip install --no-cache-dir -e .

# Create data directory
RUN mkdir -p data/sandbox data/logs data/uploads

EXPOSE 8000

CMD ["uvicorn", "aegis.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
