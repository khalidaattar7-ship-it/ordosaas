FROM python:3.12-slim

WORKDIR /app

# System dependencies for ortools and psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x start.sh

EXPOSE 8000

# start.sh runs migrations + seed, then launches uvicorn on $PORT (Render sets it).
CMD ["./start.sh"]
