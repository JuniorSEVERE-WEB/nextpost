import os
from celery import Celery

# Définir le module de settings Django par défaut pour Celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nextpost_backend.settings.local')

app = Celery('nextpost_backend')

# Utiliser la configuration Django pour Celery
app.config_from_object('django.conf:settings', namespace='CELERY')

# Découverte automatique des tâches dans les applications Django
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
