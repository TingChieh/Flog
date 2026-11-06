"""Gunicorn settings; gunicorn reads this file from the working directory.

Uploads are slow: a phone photo over a weak link, a Live Photo clip being
transcoded. A sync worker is tied up for the whole request and is killed once
`timeout` seconds pass without it finishing, which cut those uploads off
("WORKER TIMEOUT"). Threads keep a slow upload from tying up a worker, and the
generous timeout covers the processing that follows it.
"""
worker_class = 'gthread'
threads = 4
timeout = 180
graceful_timeout = 30
