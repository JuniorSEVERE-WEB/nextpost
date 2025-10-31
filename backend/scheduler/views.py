from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Q
from rest_framework.filters import OrderingFilter, SearchFilter
from django_filters.rest_framework import DjangoFilterBackend

from .models import Post, SocialAccount, PostMediaAsset
from .serializers import (
    PostSerializer, PostCreateSerializer, PostUpdateSerializer,
    SocialAccountSerializer, PostValidationSerializer
)
from .tasks import publish_post, validate_scheduled_posts

class PostViewSet(viewsets.ModelViewSet):
    """Enhanced ViewSet for managing posts with media assets and platform validation"""
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [OrderingFilter, SearchFilter, DjangoFilterBackend]
    ordering_fields = ['created_at', 'scheduled_time', 'published_at', 'updated_at']
    ordering = ['-created_at']
    search_fields = ['title', 'content']
    filterset_fields = ['status', 'social_account__platform', 'is_active']
    
    def get_queryset(self):
        """Return only posts for the authenticated user"""
        # Handle schema generation for unauthenticated users
        if getattr(self, 'swagger_fake_view', False):
            return Post.objects.none()
        
        return Post.objects.filter(user=self.request.user).select_related(
            'social_account', 'user'
        ).prefetch_related('postmediaasset_set__asset')
    
    def get_serializer_class(self):
        """Choose appropriate serializer based on action"""
        if self.action == 'create':
            return PostCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return PostUpdateSerializer
        elif self.action == 'validate_content':
            return PostValidationSerializer
        return PostSerializer
    
    @action(detail=False, methods=['get'])
    def drafts(self, request):
        """Get all draft posts"""
        drafts = self.get_queryset().filter(status=Post.PostStatus.DRAFT)
        serializer = self.get_serializer(drafts, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def scheduled(self, request):
        """Get all scheduled posts"""
        scheduled = self.get_queryset().filter(status=Post.PostStatus.SCHEDULED)
        serializer = self.get_serializer(scheduled, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def published(self, request):
        """Get all published posts"""
        published = self.get_queryset().filter(status=Post.PostStatus.PUBLISHED)
        serializer = self.get_serializer(published, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def failed(self, request):
        """Get all failed posts"""
        failed = self.get_queryset().filter(status=Post.PostStatus.FAILED)
        serializer = self.get_serializer(failed, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def publish_now(self, request, pk=None):
        """Publish a post immediately using Celery"""
        post = self.get_object()
        
        if post.status == Post.PostStatus.PUBLISHED:
            return Response(
                {'error': 'This post is already published'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if post.status == Post.PostStatus.PUBLISHING:
            return Response(
                {'error': 'This post is currently being published'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate before publishing
        validation_errors = post.validate_for_platform()
        if validation_errors:
            return Response(
                {
                    'error': 'Post validation failed',
                    'validation_errors': validation_errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Queue for immediate publication
        task = publish_post.delay(post.id, force_publish=True)
        
        return Response({
            'message': 'Post queued for immediate publication',
            'task_id': task.id,
            'post_id': post.id
        })
    
    @action(detail=True, methods=['post'])
    def cancel_schedule(self, request, pk=None):
        """Cancel post scheduling"""
        post = self.get_object()
        
        if post.status not in [Post.PostStatus.SCHEDULED, Post.PostStatus.PUBLISHING]:
            return Response(
                {'error': 'This post is not scheduled or being published'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update post status
        post.status = Post.PostStatus.CANCELLED
        post.save(update_fields=['status', 'updated_at'])
        
        serializer = self.get_serializer(post)
        return Response({
            'message': 'Post scheduling cancelled',
            'post': serializer.data
        })
    
    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """Duplicate an existing post"""
        original_post = self.get_object()
        
        # Create a copy of the post
        new_post = Post.objects.create(
            user=original_post.user,
            title=f"Copy of {original_post.title}" if original_post.title else None,
            content=original_post.content,
            social_account=original_post.social_account,
            platform_configs=original_post.platform_configs.copy(),
            status=Post.PostStatus.DRAFT,
            image=original_post.image,
            video=original_post.video
        )
        
        # Copy media assets
        for post_asset in original_post.postmediaasset_set.all():
            PostMediaAsset.objects.create(
                post=new_post,
                asset=post_asset.asset,
                order=post_asset.order,
                metadata=post_asset.metadata.copy() if post_asset.metadata else {}
            )
        
        serializer = self.get_serializer(new_post)
        return Response({
            'message': 'Post duplicated successfully',
            'post': serializer.data
        })
    
    @action(detail=True, methods=['get'])
    def validate_post(self, request, pk=None):
        """Validate a post against platform rules"""
        post = self.get_object()
        
        try:
            validation_errors = post.validate_for_platform()
            platform_rules = post.get_platform_rules()
            
            return Response({
                'is_valid': len(validation_errors) == 0,
                'validation_errors': validation_errors,
                'platform_rules': platform_rules
            })
        except Exception as e:
            return Response(
                {'error': f'Validation failed: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['post'])
    def validate_content(self, request):
        """Validate content against platform rules without saving"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        return Response(serializer.validated_data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get user post statistics"""
        queryset = self.get_queryset()
        
        stats = {
            'total': queryset.count(),
            'by_status': {
                'drafts': queryset.filter(status=Post.PostStatus.DRAFT).count(),
                'scheduled': queryset.filter(status=Post.PostStatus.SCHEDULED).count(),
                'published': queryset.filter(status=Post.PostStatus.PUBLISHED).count(),
                'failed': queryset.filter(status=Post.PostStatus.FAILED).count(),
                'publishing': queryset.filter(status=Post.PostStatus.PUBLISHING).count(),
                'cancelled': queryset.filter(status=Post.PostStatus.CANCELLED).count(),
            },
            'by_platform': {}
        }
        
        # Platform breakdown
        for platform_choice in Post.SocialPlatform.choices:
            platform = platform_choice[0]
            count = queryset.filter(social_account__platform=platform).count()
            if count > 0:
                stats['by_platform'][platform] = count
        
        return Response(stats)
    
    @action(detail=False, methods=['post'])
    def validate_all_scheduled(self, request):
        """Trigger validation of all scheduled posts"""
        task = validate_scheduled_posts.delay()
        
        return Response({
            'message': 'Validation task queued for all scheduled posts',
            'task_id': task.id
        })

class SocialAccountViewSet(viewsets.ModelViewSet):
    """Enhanced ViewSet for managing social media accounts"""
    serializer_class = SocialAccountSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [OrderingFilter, SearchFilter]
    ordering_fields = ['created_at', 'last_used_at', 'posts_count']
    ordering = ['-created_at']
    search_fields = ['username']
    
    def get_queryset(self):
        """Return only accounts for the authenticated user"""
        return SocialAccount.objects.filter(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """Toggle account active status"""
        account = self.get_object()
        account.is_active = not account.is_active
        account.save(update_fields=['is_active'])
        
        serializer = self.get_serializer(account)
        return Response({
            'message': f'Account {"activated" if account.is_active else "deactivated"}',
            'account': serializer.data
        })
    
    @action(detail=True, methods=['get'])
    def platform_capabilities(self, request, pk=None):
        """Get platform-specific capabilities and limits"""
        account = self.get_object()
        capabilities = account.get_platform_capabilities()
        
        return Response({
            'platform': account.platform,
            'capabilities': capabilities
        })
    
    @action(detail=True, methods=['get'])
    def posts(self, request, pk=None):
        """Get all posts for this social account"""
        account = self.get_object()
        posts = Post.objects.filter(
            user=request.user,
            social_account=account
        ).order_by('-created_at')
        
        # Use the PostSerializer for consistency
        from .serializers import PostSerializer
        serializer = PostSerializer(posts, many=True, context={'request': request})
        
        return Response({
            'account': self.get_serializer(account).data,
            'posts': serializer.data,
            'total_posts': posts.count()
        })
    
    @action(detail=False, methods=['get'])
    def platform_stats(self, request):
        """Get statistics by platform"""
        queryset = self.get_queryset()
        
        stats = {}
        for platform_choice in SocialAccount.SocialPlatform.choices:
            platform = platform_choice[0]
            platform_accounts = queryset.filter(platform=platform)
            
            if platform_accounts.exists():
                stats[platform] = {
                    'total_accounts': platform_accounts.count(),
                    'active_accounts': platform_accounts.filter(is_active=True).count(),
                    'total_posts': sum(acc.posts_count for acc in platform_accounts),
                    'display_name': platform_choice[1]
                }
        
        return Response(stats)
