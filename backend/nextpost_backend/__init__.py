# Intégration de Celery avec Django
from .celery import app as celery_app

__all__ = ('celery_app',)