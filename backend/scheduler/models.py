from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class SocialPlatform(models.TextChoices):
    """Plateformes de réseaux sociaux supportées"""
    FACEBOOK = 'facebook', 'Facebook'
    INSTAGRAM = 'instagram', 'Instagram'
    TWITTER = 'twitter', 'Twitter'
    LINKEDIN = 'linkedin', 'LinkedIn'
    TIKTOK = 'tiktok', 'TikTok'

class PostStatus(models.TextChoices):
    """Statuts des posts"""
    DRAFT = 'draft', 'Brouillon'
    SCHEDULED = 'scheduled', 'Planifié'
    PUBLISHED = 'published', 'Publié'
    FAILED = 'failed', 'Échec'

class Post(models.Model):
    """Modèle pour les posts à planifier"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='posts')
    content = models.TextField(help_text="Contenu du post")
    platforms = models.JSONField(default=list, help_text="Liste des plateformes cibles")
    
    # Planification
    scheduled_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(choices=PostStatus.choices, default=PostStatus.DRAFT, max_length=20)
    
    # Médias
    image = models.ImageField(upload_to='posts/images/', blank=True, null=True)
    video = models.FileField(upload_to='posts/videos/', blank=True, null=True)
    
    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    
    # Résultats
    celery_task_id = models.CharField(max_length=255, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.user.email} - {self.content[:50]}..."
    
    @property
    def is_scheduled(self):
        return self.status == PostStatus.SCHEDULED and self.scheduled_time
    
    @property
    def is_due(self):
        if not self.is_scheduled:
            return False
        return self.scheduled_time <= timezone.now()

class SocialAccount(models.Model):
    """Comptes de réseaux sociaux liés"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='social_accounts')
    platform = models.CharField(choices=SocialPlatform.choices, max_length=20)
    platform_user_id = models.CharField(max_length=255)
    username = models.CharField(max_length=255)
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True, null=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'platform', 'platform_user_id']
        
    def __str__(self):
        return f"{self.user.email} - {self.platform} ({self.username})"
