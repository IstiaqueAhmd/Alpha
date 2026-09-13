from .base import *  # noqa: F401,F403
from .base import LOGGING, REST_FRAMEWORK, env  # noqa: F401

DEBUG = False

DATABASES = {
    "default": env.db("DATABASE_URL"),
}
DATABASES["default"]["CONN_MAX_AGE"] = 60

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # A Redis hiccup should degrade (throttling briefly off) rather
            # than 500 every request that touches the cache.
            "IGNORE_EXCEPTIONS": True,
        },
    }
}

# Use cache-backed throttling in prod so worker processes share the rate-limit state.
REST_FRAMEWORK["DEFAULT_THROTTLE_CACHE"] = "default"

# Chat (apps.messaging) real-time transport + presence - in-memory in base.py
# is process-local and wrong once more than one worker process serves
# WebSocket connections, so prod always uses Redis.
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [env("REDIS_URL")]},
    },
}
CHAT_PRESENCE_BACKEND = "redis"
CHAT_PRESENCE_REDIS_URL = env("REDIS_URL")

# Security
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

LOGGING["handlers"]["file"] = {
    "class": "logging.handlers.RotatingFileHandler",
    "filename": "/app/logs/app.log",
    "maxBytes": 10 * 1024 * 1024,
    "backupCount": 5,
    "formatter": "verbose",
}
LOGGING["loggers"]["django"]["handlers"] = ["console", "file"]
LOGGING["loggers"]["apps"]["handlers"] = ["console", "file"]
