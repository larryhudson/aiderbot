# Gunicorn configuration file

# Increase the worker timeout to 300 seconds (5 minutes)
timeout = 300

# Number of worker processes
workers = 4

# Bind to localhost on port 5000
bind = "127.0.0.1:5001"

# Set the worker class to 'sync'
worker_class = 'sync'

# Enable logging
accesslog = '-'
errorlog = '-'
