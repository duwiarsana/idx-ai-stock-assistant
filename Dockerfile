# ── Build Stage ──────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies for asyncpg
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev git && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ── Runtime Stage ────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Install runtime deps for ML libraries (LightGBM, XGBoost, SHAP)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 libgomp1 && \
    rm -rf /var/lib/apt/lists/*

# Copy application code
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
