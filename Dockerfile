FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies including ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
  ffmpeg \
  gcc \
  libpq-dev \
  && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create downloads directory
RUN mkdir -p /app/downloads

# Copy cookies if available (for YouTube authentication)
# cookies.txt should be at /app/cookies.txt (same level as bot.py)
COPY cookies/cookies.txt /app/cookies.txt

# Run the bot
CMD ["python", "bot.py"]
