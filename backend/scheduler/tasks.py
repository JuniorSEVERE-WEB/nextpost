# backend/scheduler/tasks.py
import time
from celery import shared_task

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def ping(self, payload: dict | None = None):
    """
    Task de test: simule un petit traitement puis renvoie un message.
    """
    time.sleep(1)
    return {"ok": True, "echo": payload or {}}

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def publish_post(self, platform_target_id: int):
    """
    Ebauche: dans Phase 3 on viendra chercher la PlatformTarget en DB,
    valider, appeler l'adapter (FB/IG), gérer l'idempotence, etc.
    Ici on fait juste un log pour vérifier le circuit Celery.
    """
    # TODO: lookup PlatformTarget, faire la publication réelle
    return {"status": "queued", "platform_target_id": platform_target_id}
