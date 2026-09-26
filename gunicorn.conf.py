import os
bind = "0.0.0.0:" + os.environ.get("PORT", "8000")
workers = 1
worker_class = "gthread"
threads = 2
timeout = 120
accesslog = "-"
errorlog = "-"
capture_output = True
