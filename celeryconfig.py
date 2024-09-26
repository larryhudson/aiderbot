import os
## Broker settings.
broker_url = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')

worker_redirect_stdouts = False

# List of modules to import when the Celery worker starts.
imports = ('celery_tasks',)

## Using the database to store task state and results.
result_backend = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
