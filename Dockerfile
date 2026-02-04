# Use official Python lightweight image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . .

# Install the package in editable mode or normally
RUN pip install --no-cache-dir .

# Expose the dashboard port
EXPOSE 8080

# Create data directory for persistence
RUN mkdir -p /app/data

# Command to run the bot in foreground (better for Docker logs)
# Use 'youclaw' entry point directly
CMD ["youclaw", "start", "--foreground"]
