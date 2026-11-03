"""Render Free: one process, modest threads, no request-body/access logging."""
import os

bind = '0.0.0.0:' + os.getenv('PORT', '10000')
workers = 1
worker_class = 'gthread'
threads = 2
timeout = 120
graceful_timeout = 30
max_requests = 500
max_requests_jitter = 50
accesslog = None
errorlog = '-'
loglevel = 'warning'
capture_output = False
