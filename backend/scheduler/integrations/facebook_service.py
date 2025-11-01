"""
Service d'intégration Facebook/Instagram via Graph API
Gère l'authentification, la publication et la gestion d'erreurs
"""
import logging
import requests
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

class FacebookGraphAPIError(Exception):
    """Exception spécifique aux erreurs de l'API Facebook Graph"""
    def __init__(self, message: str, error_code: str = None, error_subcode: str = None):
        super().__init__(message)
        self.error_code = error_code
        self.error_subcode = error_subcode

class FacebookService:
    """Service principal pour l'intégration Facebook/Instagram"""
    
    BASE_URL = "https://graph.facebook.com/v18.0"
    
    def __init__(self):
        self.app_id = getattr(settings, 'FACEBOOK_APP_ID', '')
        self.app_secret = getattr(settings, 'FACEBOOK_APP_SECRET', '')
        
    def get_auth_url(self, redirect_uri: str, state: str = None) -> str:
        """Génère l'URL d'authentification Facebook OAuth"""
        scopes = [
            'pages_manage_posts',           # Publier sur les pages
            'pages_read_engagement',        # Lire les stats des pages  
            'instagram_basic',              # Accès de base Instagram
            'instagram_content_publish',    # Publier sur Instagram
            'pages_show_list',              # Lister les pages
        ]
        
        params = {
            'client_id': self.app_id,
            'redirect_uri': redirect_uri,
            'scope': ','.join(scopes),
            'response_type': 'code',
        }
        
        if state:
            params['state'] = state
            
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        return f"https://www.facebook.com/v18.0/dialog/oauth?{query_string}"
    
    def exchange_code_for_token(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Échange le code d'autorisation contre un access_token"""
        url = f"{self.BASE_URL}/oauth/access_token"
        
        params = {
            'client_id': self.app_id,
            'client_secret': self.app_secret,
            'redirect_uri': redirect_uri,
            'code': code,
        }
        
        response = requests.get(url, params=params)
        data = self._handle_response(response)
        
        # Étendre la durée du token (60 jours)
        long_lived_token = self._get_long_lived_token(data['access_token'])
        
        return {
            'access_token': long_lived_token['access_token'],
            'expires_in': long_lived_token.get('expires_in', 60 * 24 * 60 * 60),  # 60 jours par défaut
            'token_type': 'bearer'
        }
    
    def _get_long_lived_token(self, short_token: str) -> Dict[str, Any]:
        """Convertit un token court en token long (60 jours)"""
        url = f"{self.BASE_URL}/oauth/access_token"
        
        params = {
            'grant_type': 'fb_exchange_token',
            'client_id': self.app_id,
            'client_secret': self.app_secret,
            'fb_exchange_token': short_token,
        }
        
        response = requests.get(url, params=params)
        return self._handle_response(response)
    
    def get_user_pages(self, access_token: str) -> List[Dict[str, Any]]:
        """Récupère la liste des pages Facebook que l'utilisateur peut gérer"""
        url = f"{self.BASE_URL}/me/accounts"
        
        params = {
            'access_token': access_token,
            'fields': 'id,name,access_token,category,tasks,instagram_business_account'
        }
        
        response = requests.get(url, params=params)
        data = self._handle_response(response)
        
        pages = []
        for page_data in data.get('data', []):
            # Vérifier que l'utilisateur peut publier sur cette page
            if 'MANAGE' in page_data.get('tasks', []) and 'CREATE_CONTENT' in page_data.get('tasks', []):
                page_info = {
                    'id': page_data['id'],
                    'name': page_data['name'],
                    'access_token': page_data['access_token'],
                    'category': page_data['category'],
                    'platform': 'facebook_page'
                }
                
                # Vérifier si cette page a un compte Instagram Business lié
                if 'instagram_business_account' in page_data:
                    ig_account = page_data['instagram_business_account']
                    page_info['instagram_account'] = {
                        'id': ig_account['id'],
                        'platform': 'instagram_feed'
                    }
                
                pages.append(page_info)
        
        return pages
    
    def publish_post(self, access_token: str, platform: str, platform_user_id: str, 
                    content: str, media_urls: List[str] = None) -> Dict[str, Any]:
        """Publie un post sur Facebook ou Instagram"""
        try:
            if platform == 'facebook_page':
                return self._publish_facebook_post(access_token, platform_user_id, content, media_urls)
            elif platform in ['instagram_feed', 'instagram_story']:
                return self._publish_instagram_post(access_token, platform_user_id, content, media_urls, platform)
            else:
                raise FacebookGraphAPIError(f"Plateforme non supportée: {platform}")
                
        except requests.RequestException as e:
            logger.error(f"Erreur réseau lors de la publication: {str(e)}")
            raise FacebookGraphAPIError(f"Erreur réseau: {str(e)}")
        except Exception as e:
            logger.error(f"Erreur inattendue lors de la publication: {str(e)}")
            raise FacebookGraphAPIError(f"Erreur inattendue: {str(e)}")
    
    def _publish_facebook_post(self, access_token: str, page_id: str, 
                              content: str, media_urls: List[str] = None) -> Dict[str, Any]:
        """Publie un post sur une page Facebook"""
        url = f"{self.BASE_URL}/{page_id}/feed"
        
        data = {
            'message': content,
            'access_token': access_token,
        }
        
        # Ajouter une image si fournie
        if media_urls and len(media_urls) > 0:
            # Pour Facebook, on peut attacher une seule image directement
            data['link'] = media_urls[0]  # ou 'picture' pour une image
        
        response = requests.post(url, data=data)
        result = self._handle_response(response)
        
        return {
            'success': True,
            'platform_post_id': result['id'],
            'published_url': f"https://facebook.com/{result['id']}",
            'raw_response': result
        }
    
    def _publish_instagram_post(self, access_token: str, ig_account_id: str, 
                               content: str, media_urls: List[str], post_type: str) -> Dict[str, Any]:
        """Publie un post sur Instagram (2 étapes: créer container + publier)"""
        
        if not media_urls:
            raise FacebookGraphAPIError("Instagram nécessite au moins une image")
        
        # Étape 1: Créer le container de média
        container_id = self._create_instagram_media_container(
            access_token, ig_account_id, content, media_urls[0], post_type
        )
        
        # Étape 2: Publier le container
        return self._publish_instagram_media_container(access_token, ig_account_id, container_id)
    
    def _create_instagram_media_container(self, access_token: str, ig_account_id: str, 
                                        caption: str, image_url: str, post_type: str) -> str:
        """Crée un container de média Instagram"""
        url = f"{self.BASE_URL}/{ig_account_id}/media"
        
        data = {
            'image_url': image_url,
            'caption': caption,
            'access_token': access_token,
        }
        
        # Pour les stories, ajouter des paramètres spécifiques
        if post_type == 'instagram_story':
            data['media_type'] = 'STORIES'
        
        response = requests.post(url, data=data)
        result = self._handle_response(response)
        
        return result['id']
    
    def _publish_instagram_media_container(self, access_token: str, ig_account_id: str, 
                                         container_id: str) -> Dict[str, Any]:
        """Publie le container de média Instagram"""
        url = f"{self.BASE_URL}/{ig_account_id}/media_publish"
        
        data = {
            'creation_id': container_id,
            'access_token': access_token,
        }
        
        response = requests.post(url, data=data)
        result = self._handle_response(response)
        
        return {
            'success': True,
            'platform_post_id': result['id'],
            'published_url': f"https://instagram.com/p/{result['id']}/",
            'raw_response': result
        }
    
    def validate_token(self, access_token: str) -> Dict[str, Any]:
        """Valide un access token et retourne les informations associées"""
        url = f"{self.BASE_URL}/me"
        
        params = {
            'access_token': access_token,
            'fields': 'id,name,email'
        }
        
        response = requests.get(url, params=params)
        return self._handle_response(response)
    
    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """Gère les réponses de l'API Facebook et lève des exceptions appropriées"""
        try:
            data = response.json()
        except ValueError:
            raise FacebookGraphAPIError(f"Réponse invalide de l'API: {response.text}")
        
        if response.status_code != 200:
            error = data.get('error', {})
            error_message = error.get('message', 'Erreur inconnue')
            error_code = str(error.get('code', ''))
            error_subcode = str(error.get('error_subcode', ''))
            
            logger.error(f"Erreur API Facebook: {error_code} - {error_message}")
            
            raise FacebookGraphAPIError(
                message=error_message,
                error_code=error_code,
                error_subcode=error_subcode
            )
        
        return data


class InstagramService:
    """Service spécialisé pour Instagram (utilise Facebook Graph API)"""
    
    def __init__(self):
        self.facebook_service = FacebookService()
    
    def get_business_accounts(self, access_token: str) -> List[Dict[str, Any]]:
        """Récupère les comptes Instagram Business liés aux pages Facebook"""
        pages = self.facebook_service.get_user_pages(access_token)
        
        instagram_accounts = []
        for page in pages:
            if 'instagram_account' in page:
                ig_account = page['instagram_account']
                instagram_accounts.append({
                    'id': ig_account['id'],
                    'name': page['name'],  # Nom de la page Facebook liée
                    'access_token': page['access_token'],
                    'platform': 'instagram_feed',
                    'linked_facebook_page': page['id']
                })
        
        return instagram_accounts
    
    def publish_feed_post(self, access_token: str, account_id: str, 
                         content: str, image_url: str) -> Dict[str, Any]:
        """Publie un post sur le feed Instagram"""
        return self.facebook_service._publish_instagram_post(
            access_token, account_id, content, [image_url], 'instagram_feed'
        )
    
    def publish_story(self, access_token: str, account_id: str, 
                     content: str, image_url: str) -> Dict[str, Any]:
        """Publie une story Instagram"""
        return self.facebook_service._publish_instagram_post(
            access_token, account_id, content, [image_url], 'instagram_story'
        )