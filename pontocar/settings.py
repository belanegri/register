import os
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env(DEBUG=(bool, False))
if not os.environ.get("RAILWAY_ENVIRONMENT_ID"):
    environ.Env.read_env(BASE_DIR / ".env")
SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "core", "accounts", "dashboard", "veiculos", "estoque", "clientes", "vendas", "caixa", "contas",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "pontocar.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "core.context_processors.identidade_empresa",
    ]},
}]
WSGI_APPLICATION = "pontocar.wsgi.application"
ASGI_APPLICATION = "pontocar.asgi.application"
DATABASES = {"default": env.db("DATABASE_URL")}
if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured("Este projeto requer PostgreSQL em DATABASE_URL.")
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
# O backend default pode ser trocado por S3/R2 sem alterar os ImageFields.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard:index"
LOGOUT_REDIRECT_URL = "accounts:login"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=True)
    CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=True)
    SECURE_HSTS_SECONDS = 3600
    SECURE_CONTENT_TYPE_NOSNIFF = True


# Local continua usando pastas; produção usa um bucket privado compatível com S3.
STORAGE_MODE = env("STORAGE_MODE", default="local")
PHOTO_MAX_DIMENSION = env.int("PHOTO_MAX_DIMENSION", default=1280)
PHOTO_WEBP_QUALITY = env.int("PHOTO_WEBP_QUALITY", default=80)
PHOTO_MAX_PIXELS = env.int("PHOTO_MAX_PIXELS", default=24000000)
if not (320 <= PHOTO_MAX_DIMENSION <= 2048 and 40 <= PHOTO_WEBP_QUALITY <= 95 and 1000000 <= PHOTO_MAX_PIXELS <= 40000000):
    raise ImproperlyConfigured("Limites de imagem inválidos.")
STORAGES["comprovantes"] = {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": BASE_DIR / ".local" / "comprovantes"}}
if STORAGE_MODE == "r2":
    opcoes = {
        "access_key": env("R2_ACCESS_KEY_ID"), "secret_key": env("R2_SECRET_ACCESS_KEY"),
        "bucket_name": env("R2_BUCKET_NAME"), "endpoint_url": env("R2_ENDPOINT_URL"),
        "region_name": env("R2_REGION_NAME", default="auto"), "signature_version": "s3v4", "default_acl": None,
        "max_memory_size": 1024 * 1024,
        "querystring_auth": True, "querystring_expire": 3600, "file_overwrite": False,
        "object_parameters": {"CacheControl": "private, max-age=3600"},
    }
    STORAGES["default"] = {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": {**opcoes, "location": "fotos"}}
    STORAGES["comprovantes"] = {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": {**opcoes, "location": "comprovantes"}}
elif STORAGE_MODE != "local":
    raise ImproperlyConfigured("STORAGE_MODE deve ser local ou r2.")
if env.bool("TRUST_PROXY_HEADERS", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if os.environ.get("RAILWAY_ENVIRONMENT_ID") and (DEBUG or STORAGE_MODE != "r2"):
    raise ImproperlyConfigured("Railway requer DEBUG=False e STORAGE_MODE=r2.")
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024

# False em instalações novas; preserva identificação dos documentos legados.
LEGACY_PONTOCAR_DOCUMENTS = env.bool("LEGACY_PONTOCAR_DOCUMENTS", default=True)
