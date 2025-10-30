from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'posts', views.PostViewSet, basename='posts')
router.register(r'social-accounts', views.SocialAccountViewSet, basename='social-accounts')

urlpatterns = [
    path('', include(router.urls)),
]