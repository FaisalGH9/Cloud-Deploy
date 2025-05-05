# Base Python image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg git curl build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy all project files
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Create storage folders (optional, if used in code)
RUN mkdir -p storage/cache storage/media storage/vectors

# Expose Streamlit default port
EXPOSE 8080

# Run Streamlit app on correct port and external address
CMD ["streamlit", "run", "main.py", "--server.port=8080", "--server.address=0.0.0.0"]
