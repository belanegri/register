import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DJANGO_SETTINGS_MODULE'] = 'pontocar.test_settings'
from django.conf import settings
settings.DATABASES['default'].setdefault('TEST', {})['NAME'] = 'test_register_financeiro_20261005'
from django.core.management import execute_from_command_line
execute_from_command_line([sys.argv[0], *sys.argv[1:]])
