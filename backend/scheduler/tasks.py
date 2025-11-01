# backend/scheduler/tasks.py
import logging
import time
import traceback
from typing import Dict, Any, Optional, List
from datetime import datetime

from celery import shared_task
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Post, SocialAccount, PostMediaAsset
from media.models import MediaAsset
from .integrations.publisher import UniversalPublisher, PublicationError

logger = logging.getLogger(__name__)

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def ping(self, payload: dict | None = None):
    """
    Task de test: simule un petit traitement puis renvoie un message.
    """
    time.sleep(1)
    return {"ok": True, "echo": payload or {}}

@shared_task(bind=True, autoretry_for=(PublicationError,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def publish_post(self, post_id: int, force_publish: bool = False) -> Dict[str, Any]:
    """
    Enhanced post publishing task using the UniversalPublisher service.
    """
    try:
        post = Post.objects.select_related('user', 'social_account').get(id=post_id)
        
        # Validate post is ready for publishing
        if not force_publish and post.status != Post.PostStatus.SCHEDULED:
            logger.warning(f"Post {post_id} is not scheduled for publishing (status: {post.status})")
            return {"status": "skipped", "reason": "not_scheduled", "post_id": post_id}
        
        # Check if it's time to publish (with some tolerance)
        if not force_publish and post.scheduled_at and post.scheduled_at > timezone.now():
            logger.info(f"Post {post_id} not ready yet, scheduled for {post.scheduled_at}")
            return {"status": "deferred", "scheduled_at": post.scheduled_at.isoformat(), "post_id": post_id}
        
        logger.info(f"Starting publication of post {post_id} to {post.social_account.platform}")
        
        # Use the UniversalPublisher service
        publisher = UniversalPublisher()
        result = publisher.publish_post(post, force=force_publish)
        
        logger.info(f"Successfully published post {post_id}: {result['message']}")
        return {
            "status": "published",
            "post_id": post_id,
            "platform_post_id": result.get('platform_post_id'),
            "published_url": result.get('published_url'),
            "published_at": result.get('published_at'),
            "message": result['message']
        }
                
    except Post.DoesNotExist:
        logger.error(f"Post {post_id} not found")
        return {"status": "error", "error": "Post not found", "post_id": post_id}
    
    except PublicationError as e:
        logger.error(f"Publication error for post {post_id}: {str(e)}")
        return {
            "status": "failed",
            "post_id": post_id,
            "error": str(e),
            "platform": e.platform,
            "error_code": e.error_code
        }
    
    except Exception as e:
        logger.error(f"Unexpected error publishing post {post_id}: {str(e)}\n{traceback.format_exc()}")
        
        # Update post status to failed if it exists
        try:
            post = Post.objects.get(id=post_id)
            post.status = Post.PostStatus.FAILED
            post.error_message = f"Unexpected error: {str(e)}"[:1000]
            post.save(update_fields=['status', 'error_message', 'updated_at'])
        except Post.DoesNotExist:
            pass
        
        # Re-raise for Celery retry mechanism
        raise self.retry(countdown=60 * (self.request.retries + 1))

@shared_task(bind=True)
def publish_post_now(self, post_id: int) -> Dict[str, Any]:
    """
    Publish a post immediately, bypassing the scheduling.
    """
    return publish_post(post_id, force_publish=True)

@shared_task(bind=True)
def test_social_account_connection(self, social_account_id: int) -> Dict[str, Any]:
    """
    Test the connection of a social account to validate credentials.
    """
    try:
        social_account = SocialAccount.objects.get(id=social_account_id)
        publisher = UniversalPublisher()
        
        result = publisher.test_social_account_connection(social_account)
        
        if result['success']:
            # Update account status
            social_account.is_active = True
            social_account.last_validated_at = timezone.now()
            social_account.error_message = None
            social_account.save(update_fields=['is_active', 'last_validated_at', 'error_message'])
            
            logger.info(f"Social account {social_account_id} validated successfully")
            return {
                "status": "valid",
                "social_account_id": social_account_id,
                "platform": social_account.platform,
                "user_info": result.get('user_info', {})
            }
        else:
            # Mark account as problematic
            social_account.is_active = False
            social_account.error_message = result['error'][:500]
            social_account.save(update_fields=['is_active', 'error_message'])
            
            logger.error(f"Social account {social_account_id} validation failed: {result['error']}")
            return {
                "status": "invalid",
                "social_account_id": social_account_id,
                "error": result['error']
            }
        
    except SocialAccount.DoesNotExist:
        logger.error(f"Social account {social_account_id} not found")
        return {"status": "error", "error": "Social account not found"}
    
    except Exception as e:
        logger.error(f"Error testing social account {social_account_id}: {str(e)}")
        return {"status": "error", "error": str(e)}

# Legacy function removed - now using UniversalPublisher service

@shared_task(bind=True)
def cleanup_failed_posts(self, days_old: int = 7) -> Dict[str, Any]:
    """
    Clean up old failed posts and reset them for retry if needed.
    """
    from datetime import timedelta
    from django.utils import timezone
    
    cutoff_date = timezone.now() - timedelta(days=days_old)
    
    failed_posts = Post.objects.filter(
        status=Post.PostStatus.FAILED,
        updated_at__lt=cutoff_date
    )
    
    count = failed_posts.count()
    logger.info(f"Found {count} failed posts older than {days_old} days")
    
    # Optionally reset them to draft for manual review
    # failed_posts.update(status=Post.PostStatus.DRAFT)
    
    return {"processed": count, "cutoff_date": cutoff_date.isoformat()}

@shared_task(bind=True)
def validate_scheduled_posts(self) -> Dict[str, Any]:
    """
    Validate all scheduled posts to ensure they can be published when their time comes.
    """
    scheduled_posts = Post.objects.filter(
        status=Post.PostStatus.SCHEDULED,
        is_active=True
    ).select_related('social_account').prefetch_related('media_assets')
    
    results = {
        "total_checked": 0,
        "valid_posts": 0,
        "invalid_posts": 0,
        "errors": []
    }
    
    for post in scheduled_posts:
        results["total_checked"] += 1
        
        try:
            validation_errors = post.validate_for_platform()
            if validation_errors:
                results["invalid_posts"] += 1
                results["errors"].append({
                    "post_id": post.id,
                    "errors": validation_errors
                })
                logger.warning(f"Post {post.id} has validation errors: {validation_errors}")
            else:
                results["valid_posts"] += 1
        except Exception as e:
            results["invalid_posts"] += 1
            results["errors"].append({
                "post_id": post.id,
                "errors": [str(e)]
            })
            logger.error(f"Error validating post {post.id}: {str(e)}")
    
    logger.info(f"Validation complete: {results['valid_posts']}/{results['total_checked']} posts valid")
    return results
