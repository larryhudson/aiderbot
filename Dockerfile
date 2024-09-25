# Use an official Python runtime as a parent image
FROM python:3.12-slim-bullseye

# Set the working directory in the container
WORKDIR /app

# Install git
RUN apt-get update && apt-get install -y git && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt first to leverage Docker cache
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install -r requirements.txt

# Copy the rest of the application code
COPY . .

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Run app.py when the container launches
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "main:app"]
