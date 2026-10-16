import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','pontocar.settings')
import django
django.setup()
from django.db import connection
with connection.cursor() as c:
    c.execute("SELECT pid, datname, state, wait_event_type, wait_event, left(query,100) FROM pg_stat_activity WHERE datname LIKE 'test_%'")
    for row in c.fetchall(): print(row)
