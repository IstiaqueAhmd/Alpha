from .base import *  # noqa: F401,F403
from .base import BASE_DIR, INSTALLED_APPS, REST_FRAMEWORK

DEBUG = True
ALLOWED_HOSTS = ["*"]

# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.sqlite3",
#         "NAME": BASE_DIR / "db.sqlite3",
#     }
# }

DATABASES = {
    "default": env.db("DATABASE_URL"),
}
DATABASES["default"]["CONN_MAX_AGE"] = 60

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "getavails-dev",
    }
}


CORS_ALLOW_ALL_ORIGINS = True

# --- OpenAPI schema (drf-spectacular) - dev only -----------------------------
# Kept out of base.py on purpose: drf-spectacular lives in requirements/dev.txt,
# so prod neither installs the package nor exposes the schema endpoints.
INSTALLED_APPS = INSTALLED_APPS + ["drf_spectacular"]

REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "GetAvails API",
    "DESCRIPTION": "Django REST Framework API for the ArtistBook artist-booking platform.",
    "VERSION": "1.0.0",
    
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    "SWAGGER_UI_SETTINGS": {
        "persistAuthorization": True,
        "displayRequestDuration": True,
    },
}
