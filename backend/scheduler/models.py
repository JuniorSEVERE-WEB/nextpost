from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import MinLengthValidator
from celery import current_app
import uuid

User = get_user_model()

class SocialPlatform(models.TextChoices):
    """Plateformes de réseaux sociaux supportées avec types spécifiques"""
    FACEBOOK_PAGE = 'facebook_page', 'Facebook Page'
    FACEBOOK_GROUP = 'facebook_group', 'Facebook Groupe'
    INSTAGRAM_FEED = 'instagram_feed', 'Instagram Feed'
    INSTAGRAM_STORY = 'instagram_story', 'Instagram Story'
    INSTAGRAM_REELS = 'instagram_reels', 'Instagram Reels'
    TWITTER_POST = 'twitter_post', 'Twitter/X Post'
    LINKEDIN_PERSONAL = 'linkedin_personal', 'LinkedIn Personnel'
    LINKEDIN_COMPANY = 'linkedin_company', 'LinkedIn Entreprise'
    TIKTOK_POST = 'tiktok_post', 'TikTok Post'
    YOUTUBE_SHORT = 'youtube_short', 'YouTube Short'

class PostStatus(models.TextChoices):
    """Statuts avancés des posts"""
    DRAFT = 'draft', 'Brouillon'
    SCHEDULED = 'scheduled', 'Planifié'
    PUBLISHING = 'publishing', 'En cours de publication'
    PUBLISHED = 'published', 'Publié'
    FAILED = 'failed', 'Échec'
    CANCELLED = 'cancelled', 'Annulé'

class Post(models.Model):
    """Modèle amélioré pour les posts à planifier"""
    
    # Identifiants
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='posts')
    social_account = models.ForeignKey(
    "SocialAccount",
    on_delete=models.PROTECT,   # ou CASCADE/SET_NULL selon ta logique
    null=True, blank=True,      # <= temporaire
    related_name="posts",
)

    
    # Contenu principal
    title = models.CharField(
        max_length=200, 
        blank=True, 
        help_text="Titre optionnel pour organiser les posts"
    )
    content = models.TextField(
        validators=[MinLengthValidator(1)],
        help_text="Contenu principal du post"
    )
    
    # Plateformes ciblées (maintenu pour compatibilité)
    platforms = models.JSONField(default=list, help_text="Liste des plateformes cibles")
    
    # Configuration par plateforme (nouveau)
    platform_configs = models.JSONField(
        default=dict,
        help_text="Configuration spécifique par plateforme"
    )
    
    # Planification
    scheduled_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(choices=PostStatus.choices, default=PostStatus.DRAFT, max_length=20)
    
    # Médias (gardé pour compatibilité, mais utilisation de media_assets recommandée)
    image = models.ImageField(upload_to='posts/images/', blank=True, null=True)
    video = models.FileField(upload_to='posts/videos/', blank=True, null=True)
    
    # Nouveaux liens vers MediaAssets
    media_assets = models.ManyToManyField(
        'media.MediaAsset',
        through='PostMediaAsset',
        related_name='linked_posts',
        blank=True,
        help_text="Assets média liés à ce post"
    )
    
    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    
    # Résultats et suivi
    celery_task_id = models.CharField(max_length=255, blank=True, null=True)
    platform_post_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="ID du post sur la plateforme après publication"
    )
    error_message = models.TextField(blank=True, null=True)
    
    # Configuration globale
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['scheduled_time']),
            models.Index(fields=['created_at']),
        ]
        
    def __str__(self):
        title = self.title or self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"{self.user.email} - {title}"
    
    def clean(self):
        """Validations personnalisées"""
        super().clean()
        
        if self.scheduled_time and self.scheduled_time <= timezone.now():
            raise ValidationError("La date de planification doit être dans le futur")
    
    def save(self, *args, **kwargs):
        # Auto-scheduling : si scheduled_time est défini et pas de task Celery
        if (self.scheduled_time and 
            self.status == PostStatus.DRAFT and 
            not self.celery_task_id):
            self.status = PostStatus.SCHEDULED
            
        super().save(*args, **kwargs)
        
        # Programmer la tâche Celery après sauvegarde
        if (self.status == PostStatus.SCHEDULED and 
            self.scheduled_time and 
            not self.celery_task_id):
            self.schedule_publication()
    
    def schedule_publication(self):
        """Programmer la publication via Celery"""
        from .tasks import publish_post
        
        if self.scheduled_time and self.scheduled_time > timezone.now():
            # Programmer la tâche
            task = publish_post.apply_async(
                args=[self.id],
                eta=self.scheduled_time
            )
            
            # Sauvegarder l'ID de la tâche
            self.celery_task_id = task.id
            self.save(update_fields=['celery_task_id'])
    
    def cancel_schedule(self):
        """Annuler la planification"""
        if self.celery_task_id:
            current_app.control.revoke(self.celery_task_id, terminate=True)
            self.celery_task_id = None
            self.status = PostStatus.DRAFT
            self.save(update_fields=['celery_task_id', 'status'])
    
    @property
    def is_scheduled(self):
        return self.status == PostStatus.SCHEDULED and self.scheduled_time
    
    @property
    def is_due(self):
        if not self.is_scheduled:
            return False
        return self.scheduled_time <= timezone.now()
    
    @property
    def media_assets_count(self):
        """Nombre d'assets média liés"""
        return self.media_assets.count()
    
    @property
    def platforms_count(self):
        """Nombre de plateformes ciblées"""
        return len(self.platforms) if self.platforms else 0
    
    def get_platform_config(self, platform):
        """Obtenir la configuration pour une plateforme spécifique"""
        return self.platform_configs.get(platform, {})
    
    def set_platform_config(self, platform, config):
        """Définir la configuration pour une plateforme"""
        if not self.platform_configs:
            self.platform_configs = {}
        self.platform_configs[platform] = config
        self.save(update_fields=['platform_configs'])
    
    def validate_for_platform(self):
        """Valider le contenu pour la plateforme du compte social associé"""
        if not self.social_account:
            return ["Aucun compte social associé"]
            
        platform = self.social_account.platform
        rules = self.get_platform_rules()
        errors = []
        
        # Vérifier la longueur du contenu
        content_length = len(self.content)
        max_length = rules.get('max_length', 1000)
        if content_length > max_length:
            errors.append(f"Contenu trop long ({content_length}/{max_length} caractères)")
        
        # Vérifier les assets requis
        required_assets = rules.get('required_assets', [])
        if 'image' in required_assets:
            has_image = (self.image or 
                        self.media_assets.filter(file_type='image').exists())
            if not has_image:
                errors.append("Une image est requise pour cette plateforme")
        
        if 'video' in required_assets:
            has_video = (self.video or 
                        self.media_assets.filter(file_type='video').exists())
            if not has_video:
                errors.append("Une vidéo est requise pour cette plateforme")
        
        return errors
    
    def get_platform_rules(self):
        """Règles de validation par plateforme"""
        if not self.social_account:
            return {}
            
        platform = self.social_account.platform
        rules_map = {
            SocialPlatform.FACEBOOK_PAGE: {
                'max_length': 63206,
                'supports_images': True,
                'supports_videos': True,
                'max_images': 10,
                'max_hashtags': 30,
            },
            SocialPlatform.INSTAGRAM_FEED: {
                'max_length': 2200,
                'supports_images': True,
                'supports_videos': True,
                'max_images': 10,
                'max_hashtags': 30,
                'required_assets': ['image'],
            },
            SocialPlatform.INSTAGRAM_STORY: {
                'max_length': 2200,
                'supports_images': True,
                'supports_videos': True,
                'max_images': 1,
                'required_assets': ['image'],
                'max_video_duration': 15,
            },
            SocialPlatform.TWITTER_POST: {
                'max_length': 280,
                'supports_images': True,
                'supports_videos': True,
                'max_images': 4,
                'max_hashtags': 10,
            },
            SocialPlatform.LINKEDIN_PERSONAL: {
                'max_length': 3000,
                'supports_images': True,
                'supports_videos': True,
                'max_images': 9,
            },
            SocialPlatform.TIKTOK_POST: {
                'max_length': 2200,
                'supports_videos': True,
                'required_assets': ['video'],
                'max_video_duration': 180,
            },
        }
        
        return rules_map.get(platform, {
            'max_length': 1000,
            'supports_images': True,
            'supports_videos': False,
        })

class PostMediaAsset(models.Model):
    """Liaison entre Post et MediaAsset avec configuration"""
    
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='post_media_assets')
    asset = models.ForeignKey(
        'media.MediaAsset', 
        on_delete=models.CASCADE,
        related_name='post_usages'
    )
    
    # Configuration
    order = models.PositiveIntegerField(default=0, help_text="Ordre d'affichage")
    
    # Configuration par plateforme
    platform_configs = models.JSONField(
        default=dict,
        help_text="Configuration spécifique par plateforme (crop, filtres, etc.)"
    )
    
    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['order', 'created_at']
        unique_together = ['post', 'asset']
        indexes = [
            models.Index(fields=['post', 'order']),
        ]
    
    def __str__(self):
        return f"{self.post} - {self.asset.original_filename}"
    
    def get_platform_config(self, platform):
        """Obtenir la config pour une plateforme spécifique"""
        return self.platform_configs.get(platform, {})

class SocialAccount(models.Model):
    """Comptes de réseaux sociaux liés avec support étendu"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='social_accounts')
    platform = models.CharField(choices=SocialPlatform.choices, max_length=30)
    platform_user_id = models.CharField(max_length=255)
    username = models.CharField(max_length=255)
    
    # Tokens et authentification
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True, null=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    # Configuration avancée
    platform_config = models.JSONField(
        default=dict,
        help_text="Configuration spécifique à la plateforme"
    )
    
    # Statut et métadonnées
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    posts_count = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'platform', 'platform_user_id']
        indexes = [
            models.Index(fields=['user', 'platform']),
            models.Index(fields=['is_active']),
        ]
        
    def __str__(self):
        return f"{self.user.email} - {self.get_platform_display()} ({self.username})"
    
    def update_usage(self):
        """Mettre à jour les statistiques d'utilisation"""
        self.last_used_at = timezone.now()
        self.posts_count += 1
        self.save(update_fields=['last_used_at', 'posts_count'])
    
    def is_token_expired(self):
        """Vérifier si le token a expiré"""
        if not self.expires_at:
            return False
        return timezone.now() >= self.expires_at
    
    def get_platform_capabilities(self):
        """Obtenir les capacités de la plateforme"""
        capabilities = {
            SocialPlatform.FACEBOOK_PAGE: {
                'supports_scheduling': True,
                'supports_images': True,
                'supports_videos': True,
                'supports_carousel': True,
                'max_images': 10,
            },
            SocialPlatform.INSTAGRAM_FEED: {
                'supports_scheduling': True,
                'supports_images': True,
                'supports_videos': True,
                'supports_carousel': True,
                'max_images': 10,
                'requires_image': True,
            },
            SocialPlatform.INSTAGRAM_STORY: {
                'supports_scheduling': False,  # Stories sont généralement immédiates
                'supports_images': True,
                'supports_videos': True,
                'max_images': 1,
                'ephemeral': True,
            },
            SocialPlatform.TWITTER_POST: {
                'supports_scheduling': True,
                'supports_images': True,
                'supports_videos': True,
                'max_images': 4,
                'supports_threading': True,
            },
            SocialPlatform.LINKEDIN_PERSONAL: {
                'supports_scheduling': True,
                'supports_images': True,
                'supports_videos': True,
                'max_images': 9,
                'professional_focus': True,
            },
            SocialPlatform.TIKTOK_POST: {
                'supports_scheduling': False,  # TikTok ne supporte pas la planification
                'supports_videos': True,
                'requires_video': True,
                'vertical_format': True,
            },
        }
        
        return capabilities.get(self.platform, {
            'supports_scheduling': True,
            'supports_images': True,
        })
