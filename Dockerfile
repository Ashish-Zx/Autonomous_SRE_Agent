FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv for fast deterministic builds
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency definition
COPY requirements.txt ./

# Install python dependencies
RUN uv pip install --system -r requirements.txt

# Copy application files
COPY . .

# Initialize telemetry database
RUN python data/seed_simulator.py

EXPOSE 8501 8000

# Default command launches Streamlit War-Room
CMD ["streamlit", "run", "ui/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]

