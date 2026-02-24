FROM python:3.11-slim

# Use Yandex mirror for faster downloads in Russia
RUN sed -i 's/deb.debian.org/mirror.yandex.ru/g' /etc/apt/sources.list.d/debian.sources

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install runtime dependencies only (no build tools needed)
# - libpq5: PostgreSQL client library for psycopg2-binary
# - netcat-openbsd: for healthcheck/wait-for-db in entrypoint
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create directories for static and media files
RUN mkdir -p /app/staticfiles /app/media

# Make entrypoint executable
RUN chmod +x docker-entrypoint.sh

# Create user for security
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Run entrypoint script
ENTRYPOINT ["./docker-entrypoint.sh"]
