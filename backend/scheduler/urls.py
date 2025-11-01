from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views, oauth_views

app_name = 'scheduler'

router = DefaultRouter()
router.register(r'posts', views.PostViewSet, basename='posts')
router.register(r'social-accounts', views.SocialAccountViewSet, basename='social-accounts')

urlpatterns = [
    # API endpoints
    path('', include(router.urls)),
    
    # OAuth endpoints for Facebook/Instagram
    path('auth/facebook/start/', oauth_views.facebook_auth_start, name='facebook_auth_start'),
    path('auth/facebook/callback/', oauth_views.facebook_auth_callback, name='facebook_auth_callback'),
    
    # Social account management
    path('social-accounts/list/', oauth_views.social_accounts_list, name='social_accounts_list'),
    path('social-accounts/<int:account_id>/test/', oauth_views.test_social_account, name='test_social_account'),
    path('social-accounts/<int:account_id>/disconnect/', oauth_views.disconnect_social_account, name='disconnect_social_account'),
]