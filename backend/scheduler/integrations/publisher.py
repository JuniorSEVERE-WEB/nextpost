"""
Service de publication unifié pour toutes les plateformes
Gère la validation, la publication et le suivi des erreurs
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from django.utils import timezone

from ..models import Post, SocialAccount
from .facebook_service import FacebookService, InstagramService, FacebookGraphAPIError

logger = logging.getLogger(__name__)

class PublicationError(Exception):
    """Exception générique pour les erreurs de publication"""
    def __init__(self, message: str, platform: str = None, error_code: str = None):
        super().__init__(message)
        self.platform = platform
        self.error_code = error_code

class UniversalPublisher:
    """Service de publication unifié pour toutes les plateformes"""
    
    def __init__(self):
        self.facebook_service = FacebookService()
        self.instagram_service = InstagramService()
        
        # Mapping des plateformes vers leurs services
        self.platform_services = {
            'facebook_page': self._publish_facebook,
            'instagram_feed': self._publish_instagram_feed,
            'instagram_story': self._publish_instagram_story,
        }
    
    def validate_post_for_publication(self, post: Post) -> List[str]:
        """
        Valide qu'un post peut être publié sur sa plateforme cible
        Retourne une liste d'erreurs (vide si valide)
        """
        errors = []
        
        if not post.social_account:
            errors.append("Aucun compte social associé")
            return errors
        
        if not post.social_account.is_active:
            errors.append("Le compte social n'est pas actif")
        
        if not post.social_account.access_token:
            errors.append("Token d'accès manquant pour le compte social")
        
        # Validation spécifique à la plateforme
        platform_errors = post.validate_for_platform()
        errors.extend(platform_errors)
        
        # Validation des médias pour Instagram
        if post.social_account.platform in ['instagram_feed', 'instagram_story']:
            media_assets = post.media_assets.filter(file_type='image')
            if not media_assets.exists() and not post.image:
                errors.append("Instagram nécessite au moins une image")
        
        return errors
    
    def publish_post(self, post: Post, force: bool = False) -> Dict[str, Any]:
        """
        Publie un post sur sa plateforme cible
        
        Args:
            post: Instance du post à publier
            force: Force la publication même si le post n'est pas planifié
            
        Returns:
            Dict avec le résultat de la publication
        """
        try:
            # Validation préliminaire
            if not force and post.status != Post.PostStatus.SCHEDULED:
                raise PublicationError(f"Le post n'est pas planifié (statut: {post.status})")
            
            validation_errors = self.validate_post_for_publication(post)
            if validation_errors:
                raise PublicationError(f"Erreurs de validation: {', '.join(validation_errors)}")
            
            # Marquer le post comme en cours de publication
            post.status = Post.PostStatus.PUBLISHING
            post.save(update_fields=['status', 'updated_at'])
            
            platform = post.social_account.platform
            
            # Vérifier que la plateforme est supportée
            if platform not in self.platform_services:
                raise PublicationError(f"Plateforme non supportée: {platform}", platform=platform)
            
            # Préparer les médias
            media_urls = self._prepare_media_urls(post)
            
            # Publier via le service approprié
            logger.info(f"Publication du post {post.id} sur {platform}")
            
            publish_func = self.platform_services[platform]
            result = publish_func(post, media_urls)
            
            # Mise à jour du post avec le résultat
            post.status = Post.PostStatus.PUBLISHED
            post.published_at = timezone.now()
            post.platform_post_id = result.get('platform_post_id')
            post.error_message = None
            post.save(update_fields=[
                'status', 'published_at', 'platform_post_id', 
                'error_message', 'updated_at'
            ])
            
            # Mise à jour des statistiques du compte social
            post.social_account.posts_count += 1
            post.social_account.last_used_at = timezone.now()
            post.social_account.save(update_fields=['posts_count', 'last_used_at'])
            
            logger.info(f"Post {post.id} publié avec succès sur {platform}")
            
            return {
                'success': True,
                'platform_post_id': result.get('platform_post_id'),
                'published_url': result.get('published_url'),
                'published_at': post.published_at.isoformat(),
                'message': f'Post publié avec succès sur {post.social_account.get_platform_display()}'
            }
            
        except PublicationError:
            # Re-raise les erreurs de publication
            raise
        except FacebookGraphAPIError as e:
            error_msg = f"Erreur Facebook API: {e}"
            logger.error(f"Erreur Facebook pour le post {post.id}: {error_msg}")
            self._mark_post_failed(post, error_msg)
            raise PublicationError(error_msg, platform=platform, error_code=e.error_code)
        except Exception as e:
            error_msg = f"Erreur inattendue: {str(e)}"
            logger.error(f"Erreur inattendue pour le post {post.id}: {error_msg}")
            self._mark_post_failed(post, error_msg)
            raise PublicationError(error_msg, platform=platform)
    
    def _publish_facebook(self, post: Post, media_urls: List[str]) -> Dict[str, Any]:
        """Publie sur Facebook Page"""
        return self.facebook_service.publish_post(
            access_token=post.social_account.access_token,
            platform='facebook_page',
            platform_user_id=post.social_account.platform_user_id,
            content=post.content,
            media_urls=media_urls
        )
    
    def _publish_instagram_feed(self, post: Post, media_urls: List[str]) -> Dict[str, Any]:
        """Publie sur Instagram Feed"""
        if not media_urls:
            raise PublicationError("Instagram Feed nécessite au moins une image")
            
        return self.instagram_service.publish_feed_post(
            access_token=post.social_account.access_token,
            account_id=post.social_account.platform_user_id,
            content=post.content,
            image_url=media_urls[0]
        )
    
    def _publish_instagram_story(self, post: Post, media_urls: List[str]) -> Dict[str, Any]:
        """Publie sur Instagram Story"""
        if not media_urls:
            raise PublicationError("Instagram Story nécessite une image")
            
        return self.instagram_service.publish_story(
            access_token=post.social_account.access_token,
            account_id=post.social_account.platform_user_id,
            content=post.content,
            image_url=media_urls[0]
        )
    
    def _prepare_media_urls(self, post: Post) -> List[str]:
        """Prépare les URLs des médias pour la publication"""
        media_urls = []
        
        # URLs des MediaAssets liés
        for post_asset in post.postmediaasset_set.filter(
            asset__file_type='image'
        ).order_by('order'):
            if post_asset.asset.file:
                # Construire l'URL absolue
                # En production, cela devrait pointer vers votre CDN/stockage
                media_urls.append(post_asset.asset.file.url)
        
        # Fallback sur les champs image/video legacy
        if not media_urls:
            if post.image:
                media_urls.append(post.image.url)
            elif post.video and post.social_account.platform == 'facebook_page':
                media_urls.append(post.video.url)
        
        return media_urls
    
    def _mark_post_failed(self, post: Post, error_message: str):
        """Marque un post comme échoué avec le message d'erreur"""
        post.status = Post.PostStatus.FAILED
        post.error_message = error_message[:1000]  # Limiter la taille
        post.save(update_fields=['status', 'error_message', 'updated_at'])
    
    def test_social_account_connection(self, social_account: SocialAccount) -> Dict[str, Any]:
        """
        Teste la connexion d'un compte social
        Utile pour vérifier que les tokens sont valides
        """
        try:
            if social_account.platform == 'facebook_page':
                result = self.facebook_service.validate_token(social_account.access_token)
                return {
                    'success': True,
                    'platform': 'facebook_page',
                    'user_info': result
                }
            elif social_account.platform in ['instagram_feed', 'instagram_story']:
                result = self.facebook_service.validate_token(social_account.access_token)
                return {
                    'success': True,
                    'platform': social_account.platform,
                    'user_info': result
                }
            else:
                return {
                    'success': False,
                    'error': f'Test non supporté pour {social_account.platform}'
                }
        except FacebookGraphAPIError as e:
            return {
                'success': False,
                'error': str(e),
                'error_code': e.error_code
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Erreur inattendue: {str(e)}'
            }