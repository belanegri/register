from .settings import *  # noqa: F403

# Testes de regras e páginas não dependem de collectstatic previamente executado.
STORAGES = {
    "comprovantes": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
