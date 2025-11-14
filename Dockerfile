# Use a stable Python image
FROM python:3.10-slim

# Set working directory inside the container
WORKDIR /app

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY . .

# Default command to run your bot
CMD ["python", "main.py"]
