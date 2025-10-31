from rest_framework import serializers
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import Post, SocialAccount, PostMediaAsset, SocialPlatform
from media.models import MediaAsset
from media.serializers import MediaAssetSerializer

class SocialAccountSerializer(serializers.ModelSerializer):
    """Enhanced serializer for social media accounts with platform capabilities"""
    platform_display = serializers.CharField(source='get_platform_display', read_only=True)
    platform_capabilities = serializers.SerializerMethodField()
    
    class Meta:
        model = SocialAccount
        fields = [
            'id', 'platform', 'platform_display', 'username', 'is_active',
            'platform_config', 'posts_count', 'last_used_at',
            'platform_capabilities', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'posts_count', 'last_used_at', 'created_at', 'updated_at']

    def get_platform_capabilities(self, obj) -> dict:
        """Get platform-specific capabilities and limits"""
        return obj.get_platform_capabilities()

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)

class PostMediaAssetSerializer(serializers.ModelSerializer):
    """Serializer for post media asset relationships"""
    asset = MediaAssetSerializer(read_only=True)
    asset_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = PostMediaAsset
        fields = ['asset', 'asset_id', 'order', 'platform_configs']
        
    def validate_asset_id(self, value):
        """Validate that the asset exists and belongs to the user"""
        try:
            asset = MediaAsset.objects.get(id=value)
            request = self.context.get('request')
            if request and asset.user != request.user:
                raise serializers.ValidationError("Media asset not found or access denied")
            return value
        except MediaAsset.DoesNotExist:
            raise serializers.ValidationError("Media asset not found")

class PostCreateSerializer(serializers.ModelSerializer):
    """Enhanced serializer for creating posts with media assets and platform targeting"""
    media_assets = PostMediaAssetSerializer(many=True, required=False, write_only=True)
    social_account_id = serializers.IntegerField(write_only=True, required=True)
    
    class Meta:
        model = Post
        fields = [
            'title', 'content', 'social_account_id', 'scheduled_time',
            'platform_configs', 'media_assets', 'image', 'video'
        ]
        extra_kwargs = {
            'image': {'required': False},
            'video': {'required': False},
        }
    
    def validate_social_account_id(self, value):
        """Validate that the social account exists and belongs to the user"""
        try:
            account = SocialAccount.objects.get(id=value, user=self.context['request'].user)
            if not account.is_active:
                raise serializers.ValidationError("Social account is not active")
            return value
        except SocialAccount.DoesNotExist:
            raise serializers.ValidationError("Social account not found or access denied")
    
    def validate_scheduled_time(self, value):
        """Validate that scheduled time is in the future"""
        if value and value <= timezone.now():
            raise serializers.ValidationError("Scheduled time must be in the future")
        return value
    
    def validate_content(self, value):
        """Basic content validation"""
        if not value or len(value.strip()) < 1:
            raise serializers.ValidationError("Content cannot be empty")
        if len(value) > 10000:  # Generous limit, platform-specific validation happens later
            raise serializers.ValidationError("Content is too long")
        return value
    
    def validate(self, attrs):
        """Cross-field validation including platform-specific rules"""
        # Get the social account for platform-specific validation
        social_account = SocialAccount.objects.get(
            id=attrs['social_account_id'], 
            user=self.context['request'].user
        )
        
        # Create a temporary post instance for validation
        temp_post = Post(
            title=attrs.get('title', ''),
            content=attrs['content'],
            social_account=social_account,
            platform_configs=attrs.get('platform_configs', {})
        )
        
        # Platform-specific validation
        try:
            validation_errors = temp_post.validate_for_platform()
            if validation_errors:
                raise serializers.ValidationError({
                    'platform_validation': validation_errors
                })
        except Exception as e:
            raise serializers.ValidationError({
                'platform_validation': [str(e)]
            })
        
        return attrs
    
    def create(self, validated_data):
        media_assets_data = validated_data.pop('media_assets', [])
        
        # Set user and determine status
        validated_data['user'] = self.context['request'].user
        
        if validated_data.get('scheduled_time'):
            validated_data['status'] = Post.PostStatus.SCHEDULED
        else:
            validated_data['status'] = Post.PostStatus.DRAFT
        
        # Create the post
        post = super().create(validated_data)
        
        # Create media asset relationships
        for i, asset_data in enumerate(media_assets_data):
            PostMediaAsset.objects.create(
                post=post,
                asset_id=asset_data['asset_id'],
                order=i,
                platform_configs=asset_data.get('platform_configs', {})
            )
        
        return post

class PostSerializer(serializers.ModelSerializer):
    """Enhanced complete serializer for posts with media assets and platform info"""
    user_email = serializers.CharField(source='user.email', read_only=True)
    social_account = SocialAccountSerializer(read_only=True)
    media_assets = serializers.SerializerMethodField()
    platform_display = serializers.CharField(source='social_account.get_platform_display', read_only=True)
    platform_validation_status = serializers.SerializerMethodField()
    is_scheduled = serializers.BooleanField(read_only=True)
    is_due = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Post
        fields = [
            'id', 'title', 'content', 'user_email', 'social_account',
            'platform_display', 'scheduled_time', 'status', 'is_active',
            'platform_configs', 'media_assets', 'image', 'video',
            'created_at', 'updated_at', 'published_at', 'platform_post_id',
            'is_scheduled', 'is_due', 'platform_validation_status',
            'error_message'
        ]
        read_only_fields = [
            'id', 'user_email', 'created_at', 'updated_at', 
            'published_at', 'is_scheduled', 'is_due',
            'platform_post_id', 'error_message'
        ]
    
    def get_media_assets(self, obj) -> list:
        """Get ordered media assets for the post"""
        return PostMediaAssetSerializer(
            obj.postmediaasset_set.all().order_by('order'), 
            many=True
        ).data
    
    def get_platform_validation_status(self, obj) -> dict:
        """Get platform validation status"""
        try:
            errors = obj.validate_for_platform()
            return {
                'is_valid': len(errors) == 0,
                'errors': errors
            }
        except Exception as e:
            return {
                'is_valid': False,
                'errors': [str(e)]
            }

class PostUpdateSerializer(serializers.ModelSerializer):
    """Enhanced serializer for updating posts with media asset management"""
    media_assets = PostMediaAssetSerializer(many=True, required=False, write_only=True)
    
    class Meta:
        model = Post
        fields = [
            'title', 'content', 'scheduled_time', 'platform_configs',
            'media_assets', 'image', 'video', 'is_active'
        ]
    
    def validate_scheduled_time(self, value):
        """Only allow modification if post is not published"""
        if self.instance.status == Post.PostStatus.PUBLISHED:
            raise serializers.ValidationError("Cannot modify a published post")
        
        if value and value <= timezone.now():
            raise serializers.ValidationError("Scheduled time must be in the future")
        
        return value
    
    def validate(self, attrs):
        """Platform-specific validation for updates"""
        if not self.instance:
            return attrs
            
        # Create updated instance for validation
        temp_instance = self.instance
        for key, value in attrs.items():
            if key != 'media_assets':  # Skip media_assets for now
                setattr(temp_instance, key, value)
        
        # Platform validation
        try:
            validation_errors = temp_instance.validate_for_platform()
            if validation_errors:
                raise serializers.ValidationError({
                    'platform_validation': validation_errors
                })
        except Exception as e:
            raise serializers.ValidationError({
                'platform_validation': [str(e)]
            })
        
        return attrs
    
    def update(self, instance, validated_data):
        media_assets_data = validated_data.pop('media_assets', None)
        
        # Update status based on scheduling
        if 'scheduled_time' in validated_data:
            if validated_data['scheduled_time']:
                instance.status = Post.PostStatus.SCHEDULED
            else:
                instance.status = Post.PostStatus.DRAFT
        
        # Update the post
        instance = super().update(instance, validated_data)
        
        # Update media assets if provided
        if media_assets_data is not None:
            # Remove existing media assets
            instance.postmediaasset_set.all().delete()
            
            # Add new media assets
            for i, asset_data in enumerate(media_assets_data):
                PostMediaAsset.objects.create(
                    post=instance,
                    asset_id=asset_data['asset_id'],
                    order=i,
                    platform_configs=asset_data.get('platform_configs', {})
                )
        
        return instance

class PostValidationSerializer(serializers.Serializer):
    """Serializer for validating post content against platform rules"""
    content = serializers.CharField()
    platform = serializers.ChoiceField(choices=SocialPlatform.choices)
    media_asset_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True
    )
    
    def validate(self, attrs):
        """Validate content against platform rules"""
        # Create temporary post for validation
        temp_post = Post(
            content=attrs['content'],
            social_account=SocialAccount(platform=attrs['platform'])
        )
        
        # Add media assets for validation if provided
        if attrs.get('media_asset_ids'):
            # In a real implementation, you'd fetch and validate these assets
            pass
        
        validation_errors = temp_post.validate_for_platform()
        
        return {
            'is_valid': len(validation_errors) == 0,
            'errors': validation_errors,
            'platform_rules': temp_post.get_platform_rules()
        }

class PostValidationSerializer(serializers.Serializer):
    """Serializer for validating post content without saving"""
    content = serializers.CharField(max_length=10000)
    platform = serializers.ChoiceField(choices=SocialPlatform.choices)
    media_asset_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True
    )
    
    def validate(self, attrs):
        """Validate content against platform rules"""
        from .models import SocialAccount
        
        # Create a temporary social account for validation
        temp_account = SocialAccount(platform=attrs['platform'])
        
        # Create a temporary post for validation
        temp_post = Post(
            content=attrs['content'],
            social_account=temp_account
        )
        
        validation_errors = temp_post.validate_for_platform()
        platform_rules = temp_post.get_platform_rules()
        
        return {
            'content': attrs['content'],
            'platform': attrs['platform'],
            'is_valid': len(validation_errors) == 0,
            'validation_errors': validation_errors,
            'platform_rules': platform_rules
        }