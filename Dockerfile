FROM python:3.11-slim

# System deps for CAN + terminal
RUN apt-get update && apt-get install -y --no-install-recommends \
    can-utils \
    procps \
    bash \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cache layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e . 2>/dev/null || pip install --no-cache-dir \
    "fastapi>=0.104" \
    "uvicorn[standard]>=0.24" \
    "python-can>=4.3" \
    "cantools>=39.0" \
    "jinja2>=3.1" \
    "pyyaml>=6.0" \
    "pydantic>=2.0" \
    "aiohttp>=3.9" \
    "websockets>=12.0" \
    "paho-mqtt>=1.6,<2"

# Copy dashboard code
COPY . .

# Install the package
RUN pip install --no-cache-dir -e .

EXPOSE 8088

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8088"]
