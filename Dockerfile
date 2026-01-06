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

# Run the bot
CMD ["python", "bot.py"]
