# Use official Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source files
COPY . .

# Expose port
EXPOSE 8080

# Run Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
