import os
bind = "0.0.0.0:" + os.environ.get("PORT", "8000")
workers = 1
worker_class = "gthread"
threads = 2
timeout = 120
accesslog = "-"
# Não registrar query strings: o callback OAuth recebe um código temporário.
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s'
errorlog = "-"
capture_output = True
