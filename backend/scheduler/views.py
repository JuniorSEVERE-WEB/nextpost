from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from rest_framework.filters import OrderingFilter, SearchFilter

from .models import Post, SocialAccount, PostStatus
from .serializers import (
    PostSerializer, PostCreateSerializer, PostUpdateSerializer,
    SocialAccountSerializer
)

class PostViewSet(viewsets.ModelViewSet):
    """ViewSet pour gérer les posts"""
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [OrderingFilter, SearchFilter]
    ordering_fields = ['created_at', 'scheduled_time', 'published_at']
    ordering = ['-created_at']
    search_fields = ['content']
    
    def get_queryset(self):
        """Retourner seulement les posts de l'utilisateur connecté"""
        return Post.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        """Choisir le bon serializer selon l'action"""
        if self.action == 'create':
            return PostCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return PostUpdateSerializer
        return PostSerializer
    
    @action(detail=False, methods=['get'])
    def drafts(self, request):
        """Récupérer tous les brouillons"""
        drafts = self.get_queryset().filter(status=PostStatus.DRAFT)
        serializer = self.get_serializer(drafts, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def scheduled(self, request):
        """Récupérer tous les posts planifiés"""
        scheduled = self.get_queryset().filter(status=PostStatus.SCHEDULED)
        serializer = self.get_serializer(scheduled, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def published(self, request):
        """Récupérer tous les posts publiés"""
        published = self.get_queryset().filter(status=PostStatus.PUBLISHED)
        serializer = self.get_serializer(published, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def publish_now(self, request, pk=None):
        """Publier immédiatement un post"""
        post = self.get_object()
        
        if post.status == PostStatus.PUBLISHED:
            return Response(
                {'error': 'Ce post est déjà publié'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # TODO: Ici on ajoutera la logique de publication via Celery
        # Pour l'instant, on simule la publication
        post.status = PostStatus.PUBLISHED
        post.published_at = timezone.now()
        post.save()
        
        serializer = self.get_serializer(post)
        return Response({
            'message': 'Post publié avec succès',
            'post': serializer.data
        })
    
    @action(detail=True, methods=['post'])
    def cancel_schedule(self, request, pk=None):
        """Annuler la planification d'un post"""
        post = self.get_object()
        
        if post.status != PostStatus.SCHEDULED:
            return Response(
                {'error': 'Ce post n\'est pas planifié'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # TODO: Annuler la tâche Celery si elle existe
        post.status = PostStatus.DRAFT
        post.scheduled_time = None
        post.celery_task_id = None
        post.save()
        
        serializer = self.get_serializer(post)
        return Response({
            'message': 'Planification annulée',
            'post': serializer.data
        })
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Statistiques des posts de l'utilisateur"""
        queryset = self.get_queryset()
        
        stats = {
            'total': queryset.count(),
            'drafts': queryset.filter(status=PostStatus.DRAFT).count(),
            'scheduled': queryset.filter(status=PostStatus.SCHEDULED).count(),
            'published': queryset.filter(status=PostStatus.PUBLISHED).count(),
            'failed': queryset.filter(status=PostStatus.FAILED).count(),
        }
        
        return Response(stats)

class SocialAccountViewSet(viewsets.ModelViewSet):
    """ViewSet pour gérer les comptes de réseaux sociaux"""
    serializer_class = SocialAccountSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Retourner seulement les comptes de l'utilisateur connecté"""
        return SocialAccount.objects.filter(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """Activer/désactiver un compte"""
        account = self.get_object()
        account.is_active = not account.is_active
        account.save()
        
        serializer = self.get_serializer(account)
        return Response({
            'message': f'Compte {"activé" if account.is_active else "désactivé"}',
            'account': serializer.data
        })
