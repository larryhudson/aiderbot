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
ENV CELERY_BROKER_URL=${CELERY_BROKER_URL}
ENV CELERY_RESULT_BACKEND=${CELERY_RESULT_BACKEND}
ENV ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}

# Create a script to choose which process to run
RUN echo '#!/bin/bash\n\
if [ "$FLY_PROCESS_GROUP" == "app" ]; then\n\
    exec gunicorn --bind 0.0.0.0:8585 main:app\n\
elif [ "$FLY_PROCESS_GROUP" == "worker" ]; then\n\
    exec celery -A celery_tasks worker --loglevel=info\n\
else\n\
    echo "Unknown process group: $FLY_PROCESS_GROUP"\n\
    exit 1\n\
fi' > /app/start.sh && chmod +x /app/start.sh

# Set the entrypoint to our new script
ENTRYPOINT ["/app/start.sh"]
