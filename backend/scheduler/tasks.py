# backend/scheduler/tasks.py
import logging
import time
import traceback
from typing import Dict, Any, Optional, List
from datetime import datetime

from celery import shared_task
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Post, SocialAccount, PostMediaAsset
from media.models import MediaAsset

logger = logging.getLogger(__name__)

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def ping(self, payload: dict | None = None):
    """
    Task de test: simule un petit traitement puis renvoie un message.
    """
    time.sleep(1)
    return {"ok": True, "echo": payload or {}}

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def publish_post(self, post_id: int, force_publish: bool = False) -> Dict[str, Any]:
    """
    Enhanced post publishing task with platform validation and media asset handling.
    """
    try:
        with transaction.atomic():
            # Get post with related data
            post = Post.objects.select_related('user', 'social_account').prefetch_related(
                'media_assets__asset'
            ).get(id=post_id)
            
            # Validate post is ready for publishing
            if not force_publish and post.status != Post.PostStatus.SCHEDULED:
                logger.warning(f"Post {post_id} is not scheduled for publishing (status: {post.status})")
                return {"status": "skipped", "reason": "not_scheduled", "post_id": post_id}
            
            # Check if social account is active and valid
            if not post.social_account or not post.social_account.is_active:
                raise ValidationError("Social account is not active or missing")
            
            # Update status to publishing
            post.status = Post.PostStatus.PUBLISHING
            post.save(update_fields=['status', 'updated_at'])
            
            logger.info(f"Starting publication of post {post_id} to {post.social_account.platform}")
            
            # Platform-specific validation
            validation_errors = post.validate_for_platform()
            if validation_errors:
                post.status = Post.PostStatus.FAILED
                post.error_message = f"Validation errors: {', '.join(validation_errors)}"
                post.save(update_fields=['status', 'error_message', 'updated_at'])
                raise ValidationError(f"Post validation failed: {validation_errors}")
            
            # Prepare media assets for publication
            media_files = []
            for post_asset in post.postmediaasset_set.all().order_by('order'):
                asset = post_asset.asset
                media_files.append({
                    'type': asset.file_type,
                    'path': asset.file.path,
                    'url': asset.file.url,
                    'thumbnail_url': asset.thumbnail.url if asset.thumbnail else None,
                    'metadata': asset.metadata
                })
            
            # Platform-specific publishing logic
            result = _publish_to_platform(post, media_files)
            
            if result['success']:
                # Update post with success status
                post.status = Post.PostStatus.PUBLISHED
                post.published_at = datetime.now()
                post.platform_post_id = result.get('platform_post_id')
                post.error_message = None
                post.save(update_fields=['status', 'published_at', 'platform_post_id', 'error_message', 'updated_at'])
                
                # Update social account usage stats
                post.social_account.posts_count += 1
                post.social_account.last_used_at = datetime.now()
                post.social_account.save(update_fields=['posts_count', 'last_used_at'])
                
                logger.info(f"Successfully published post {post_id}")
                return {
                    "status": "published",
                    "post_id": post_id,
                    "platform_post_id": result.get('platform_post_id'),
                    "published_at": post.published_at.isoformat()
                }
            else:
                # Handle publishing failure
                post.status = Post.PostStatus.FAILED
                post.error_message = result.get('error', 'Unknown publishing error')
                post.save(update_fields=['status', 'error_message', 'updated_at'])
                
                logger.error(f"Failed to publish post {post_id}: {result.get('error')}")
                return {
                    "status": "failed",
                    "post_id": post_id,
                    "error": result.get('error')
                }
                
    except Post.DoesNotExist:
        logger.error(f"Post {post_id} not found")
        return {"status": "error", "error": "Post not found", "post_id": post_id}
    
    except Exception as e:
        logger.error(f"Error publishing post {post_id}: {str(e)}\n{traceback.format_exc()}")
        
        # Update post status to failed if it exists
        try:
            post = Post.objects.get(id=post_id)
            post.status = Post.PostStatus.FAILED
            post.error_message = f"Publishing error: {str(e)}"
            post.save(update_fields=['status', 'error_message', 'updated_at'])
        except Post.DoesNotExist:
            pass
        
        # Re-raise for Celery retry mechanism
        raise self.retry(countdown=60 * (self.request.retries + 1))

def _publish_to_platform(post: Post, media_files: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Platform-specific publishing logic. This is a placeholder that would be
    replaced with actual API calls to each platform.
    """
    platform = post.social_account.platform
    
    # Simulate platform-specific publishing
    logger.info(f"Publishing to {platform} with {len(media_files)} media files")
    
    # Platform-specific logic would go here
    # For now, simulate success/failure
    try:
        if platform == 'instagram_story' and not media_files:
            return {"success": False, "error": "Instagram Stories require at least one media file"}
        
        if platform in ['facebook_page', 'facebook_group'] and len(post.content) > 63206:
            return {"success": False, "error": "Facebook posts cannot exceed 63,206 characters"}
        
        if platform == 'twitter' and len(post.content) > 280:
            return {"success": False, "error": "Twitter posts cannot exceed 280 characters"}
        
        # Simulate successful publication
        import uuid
        platform_post_id = f"{platform}_{uuid.uuid4().hex[:8]}"
        
        return {
            "success": True,
            "platform_post_id": platform_post_id,
            "published_url": f"https://{platform}.com/posts/{platform_post_id}"
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

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
