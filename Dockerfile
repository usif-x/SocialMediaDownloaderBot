FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
# Playwright image has browser deps, but we need ffmpeg and xvfb for our specific usage
RUN apt-get update && apt-get install -y --no-install-recommends \
  ffmpeg \
  gcc \
  libpq-dev \
  xvfb \
  && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Browsers are already installed in this image, so we don't need 'playwright install'

# Copy project files
COPY . .

# Create downloads directory
RUN mkdir -p /app/downloads

# Copy cookies if available (for YouTube authentication)
# cookies.txt should be at /app/cookies.txt (same level as bot.py)
COPY cookies/cookies.txt /app/cookies.txt

# Run the bot
CMD ["python", "bot.py"]
