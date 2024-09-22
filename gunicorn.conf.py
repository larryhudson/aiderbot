# Gunicorn configuration file

# Increase the worker timeout to 120 seconds (2 minutes)
timeout = 120

# Number of worker processes
workers = 4

# Bind to localhost on port 5000
bind = "127.0.0.1:5000"

# Set the worker class to 'sync'
worker_class = 'sync'

# Enable logging
accesslog = '-'
errorlog = '-'
