"""
gunicorn settings for production (docker-compose-prod.yml); gunicorn reads this file
from the working directory.

gunicorn's own default is a single worker that handles one request at a time, so one
slow request would stop the whole site. Here each worker handles several at once.
"""

import os

bind = '0.0.0.0:8000'
# Processes. Raise WEB_CONCURRENCY on a server with more CPU cores and memory.
workers = int(os.environ.get('WEB_CONCURRENCY', 2))
# Requests each worker handles at the same time
worker_class = 'gthread'
threads = 4
# gunicorn's control interface (gunicornc) wants a socket file in the working directory,
# which the container's user can't write to. Nothing here uses it.
control_socket_disable = True
