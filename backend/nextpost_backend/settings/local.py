from .base import *

# Settings de développement local
DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']

# CORS pour développement
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# Base de données locale (utilise la configuration de base.py)

# Email backend pour développement (console)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
