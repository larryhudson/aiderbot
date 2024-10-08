# Use an official Python runtime as a parent image
FROM python:3.12-slim-bullseye

# Set the working directory in the container
WORKDIR /app

# Install git, pandoc, and set up environment
RUN apt-get update && apt-get install -y git pandoc && apt-get clean && rm -rf /var/lib/apt/lists/*
ENV GIT_PYTHON_GIT_EXECUTABLE=/usr/bin/git

# Set Git username from environment variable
ARG GIT_COMMIT_AUTHOR_NAME
ARG GIT_COMMIT_AUTHOR_EMAIL
ENV GIT_COMMIT_AUTHOR_NAME=${GIT_COMMIT_AUTHOR_NAME}
ENV GIT_COMMIT_AUTHOR_EMAIL=${GIT_COMMIT_AUTHOR_EMAIL}
RUN git config --global user.name "${GIT_COMMIT_AUTHOR_NAME}"
RUN git config --global user.email "${GIT_COMMIT_AUTHOR_EMAIL}"

# Copy requirements.txt first to leverage Docker cache
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install -r requirements.txt

# Install Playwright with Chromium
RUN python -m playwright install --with-deps chromium

# Copy the rest of the application code
COPY . .

# Set environment variables
ENV FLASK_ENV=production
ENV REDIS_URL=${REDIS_URL}
ENV ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
