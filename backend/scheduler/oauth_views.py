"""
Vues pour l'authentification OAuth avec Facebook/Instagram
"""
import logging
from typing import Dict, Any
from urllib.parse import urlencode

from django.shortcuts import redirect
from django.urls import reverse
from django.http import JsonResponse, HttpResponseBadRequest
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.utils import timezone

from .models import SocialAccount
from .integrations.facebook_service import FacebookService, FacebookGraphAPIError

logger = logging.getLogger(__name__)

@login_required
@require_http_methods(["GET"])
def facebook_auth_start(request):
    """
    Démarre le processus d'authentification OAuth Facebook
    """
    try:
        platform = request.GET.get('platform', 'facebook_page')
        
        # Valider que la plateforme est supportée
        if platform not in ['facebook_page', 'instagram_feed', 'instagram_story']:
            return JsonResponse({
                'error': f'Plateforme non supportée: {platform}'
            }, status=400)
        
        facebook_service = FacebookService()
        
        # Construire l'URL de callback
        callback_url = request.build_absolute_uri(reverse('scheduler:facebook_auth_callback'))
        
        # Générer l'URL d'autorisation Facebook
        auth_url = facebook_service.get_auth_url(
            redirect_uri=callback_url,
            state=f"{request.user.id}:{platform}"  # Inclure l'utilisateur et la plateforme
        )
        
        logger.info(f"User {request.user.id} starting Facebook OAuth for {platform}")
        
        return JsonResponse({
            'auth_url': auth_url,
            'platform': platform
        })
        
    except Exception as e:
        logger.error(f"Error starting Facebook OAuth: {str(e)}")
        return JsonResponse({
            'error': 'Erreur lors du démarrage de l\'authentification'
        }, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def facebook_auth_callback(request):
    """
    Gère le callback OAuth de Facebook
    """
    try:
        # Récupérer les paramètres du callback
        code = request.GET.get('code')
        state = request.GET.get('state')
        error = request.GET.get('error')
        
        if error:
            error_description = request.GET.get('error_description', 'Authentification annulée')
            logger.warning(f"Facebook OAuth error: {error} - {error_description}")
            return redirect(f"/dashboard/social-accounts?error={error}")
        
        if not code or not state:
            logger.error("Missing code or state in Facebook callback")
            return HttpResponseBadRequest("Paramètres manquants")
        
        # Décoder le state (user_id:platform)
        try:
            user_id, platform = state.split(':', 1)
            user_id = int(user_id)
        except (ValueError, AttributeError):
            logger.error(f"Invalid state format: {state}")
            return HttpResponseBadRequest("State invalide")
        
        # Vérifier que l'utilisateur existe (sécurité)
        from django.contrib.auth.models import User
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.error(f"User {user_id} not found")
            return HttpResponseBadRequest("Utilisateur non trouvé")
        
        facebook_service = FacebookService()
        callback_url = request.build_absolute_uri(reverse('scheduler:facebook_auth_callback'))
        
        # Échanger le code contre un token d'accès
        token_data = facebook_service.exchange_code_for_token(code, callback_url)
        
        if platform == 'facebook_page':
            # Pour Facebook Page, récupérer les pages disponibles
            pages = facebook_service.get_user_pages(token_data['access_token'])
            
            if pages:
                # Prendre la première page ou permettre à l'utilisateur de choisir
                page = pages[0]  # Pour simplifier, on prend la première
                
                # Créer ou mettre à jour le compte social
                social_account, created = SocialAccount.objects.update_or_create(
                    user=user,
                    platform='facebook_page',
                    platform_user_id=page['id'],
                    defaults={
                        'platform_username': page['name'],
                        'access_token': page['access_token'],  # Token de la page
                        'token_expires_at': timezone.now() + timezone.timedelta(days=60),  # Long-lived token
                        'is_active': True,
                        'last_validated_at': timezone.now(),
                        'platform_config': {
                            'page_name': page['name'],
                            'page_category': page.get('category', ''),
                            'permissions': page.get('perms', [])
                        }
                    }
                )
                
                action = 'créé' if created else 'mis à jour'
                logger.info(f"Facebook page account {action} for user {user_id}: {page['name']}")
                
            else:
                logger.warning(f"No Facebook pages found for user {user_id}")
                return redirect("/dashboard/social-accounts?error=no_pages")
            
        elif platform in ['instagram_feed', 'instagram_story']:
            # Pour Instagram, récupérer le compte Instagram Business
            instagram_accounts = facebook_service.get_instagram_business_accounts(token_data['access_token'])
            
            if instagram_accounts:
                # Prendre le premier compte Instagram ou permettre de choisir
                ig_account = instagram_accounts[0]
                
                # Créer ou mettre à jour le compte social
                social_account, created = SocialAccount.objects.update_or_create(
                    user=user,
                    platform=platform,
                    platform_user_id=ig_account['id'],
                    defaults={
                        'platform_username': ig_account['username'],
                        'access_token': token_data['access_token'],  # Token Facebook
                        'token_expires_at': timezone.now() + timezone.timedelta(days=60),
                        'is_active': True,
                        'last_validated_at': timezone.now(),
                        'platform_config': {
                            'instagram_account_id': ig_account['id'],
                            'username': ig_account['username'],
                            'account_type': ig_account.get('account_type', 'BUSINESS')
                        }
                    }
                )
                
                action = 'créé' if created else 'mis à jour'
                logger.info(f"Instagram account {action} for user {user_id}: {ig_account['username']}")
                
            else:
                logger.warning(f"No Instagram Business accounts found for user {user_id}")
                return redirect("/dashboard/social-accounts?error=no_instagram")
        
        # Rediriger vers le dashboard avec succès
        return redirect("/dashboard/social-accounts?success=connected")
        
    except FacebookGraphAPIError as e:
        logger.error(f"Facebook API error in callback: {str(e)}")
        return redirect(f"/dashboard/social-accounts?error=api_error")
    
    except Exception as e:
        logger.error(f"Unexpected error in Facebook callback: {str(e)}")
        return redirect(f"/dashboard/social-accounts?error=unexpected")

@login_required
@require_http_methods(["POST"])
def disconnect_social_account(request, account_id):
    """
    Déconnecte un compte social (supprime ou désactive)
    """
    try:
        social_account = SocialAccount.objects.get(
            id=account_id,
            user=request.user
        )
        
        # Désactiver le compte plutôt que le supprimer pour garder l'historique
        social_account.is_active = False
        social_account.access_token = ''  # Effacer le token
        social_account.error_message = 'Déconnecté par l\'utilisateur'
        social_account.save(update_fields=['is_active', 'access_token', 'error_message'])
        
        logger.info(f"User {request.user.id} disconnected social account {account_id}")
        
        return JsonResponse({
            'success': True,
            'message': f'Compte {social_account.get_platform_display()} déconnecté'
        })
        
    except SocialAccount.DoesNotExist:
        return JsonResponse({
            'error': 'Compte social non trouvé'
        }, status=404)
    
    except Exception as e:
        logger.error(f"Error disconnecting social account {account_id}: {str(e)}")
        return JsonResponse({
            'error': 'Erreur lors de la déconnexion'
        }, status=500)

@login_required
@require_http_methods(["POST"])
def test_social_account(request, account_id):
    """
    Teste la connexion d'un compte social
    """
    try:
        social_account = SocialAccount.objects.get(
            id=account_id,
            user=request.user
        )
        
        # Utiliser la tâche Celery pour tester
        from .tasks import test_social_account_connection
        
        # Lancer le test en arrière-plan
        task = test_social_account_connection.delay(social_account.id)
        
        return JsonResponse({
            'success': True,
            'task_id': task.id,
            'message': 'Test de connexion lancé'
        })
        
    except SocialAccount.DoesNotExist:
        return JsonResponse({
            'error': 'Compte social non trouvé'
        }, status=404)
    
    except Exception as e:
        logger.error(f"Error testing social account {account_id}: {str(e)}")
        return JsonResponse({
            'error': 'Erreur lors du test'
        }, status=500)

@login_required
@require_http_methods(["GET"])
def social_accounts_list(request):
    """
    Liste les comptes sociaux de l'utilisateur
    """
    try:
        accounts = SocialAccount.objects.filter(
            user=request.user
        ).order_by('platform', '-created_at')
        
        accounts_data = []
        for account in accounts:
            accounts_data.append({
                'id': account.id,
                'platform': account.platform,
                'platform_display': account.get_platform_display(),
                'username': account.platform_username,
                'is_active': account.is_active,
                'posts_count': account.posts_count,
                'last_used_at': account.last_used_at.isoformat() if account.last_used_at else None,
                'last_validated_at': account.last_validated_at.isoformat() if account.last_validated_at else None,
                'error_message': account.error_message,
                'created_at': account.created_at.isoformat()
            })
        
        return JsonResponse({
            'accounts': accounts_data,
            'total': len(accounts_data)
        })
        
    except Exception as e:
        logger.error(f"Error listing social accounts for user {request.user.id}: {str(e)}")
        return JsonResponse({
            'error': 'Erreur lors de la récupération des comptes'
        }, status=500)