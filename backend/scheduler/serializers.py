from rest_framework import serializers
from django.utils import timezone
from .models import Post, SocialAccount, PostStatus, SocialPlatform

class SocialAccountSerializer(serializers.ModelSerializer):
    """Serializer pour les comptes de réseaux sociaux"""
    
    class Meta:
        model = SocialAccount
        fields = [
            'id', 'platform', 'username', 'is_active', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        # L'utilisateur est automatiquement assigné via la vue
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)

class PostCreateSerializer(serializers.ModelSerializer):
    """Serializer pour créer un post"""
    
    class Meta:
        model = Post
        fields = [
            'content', 'platforms', 'scheduled_time', 
            'image', 'video'
        ]
    
    def validate_platforms(self, value):
        """Valider que les plateformes sont supportées"""
        if not value:
            raise serializers.ValidationError("Au moins une plateforme doit être sélectionnée.")
        
        valid_platforms = [choice[0] for choice in SocialPlatform.choices]
        for platform in value:
            if platform not in valid_platforms:
                raise serializers.ValidationError(f"Plateforme non supportée: {platform}")
        
        return value
    
    def validate_scheduled_time(self, value):
        """Valider que la date de planification est dans le futur"""
        if value and value <= timezone.now():
            raise serializers.ValidationError("La date de planification doit être dans le futur.")
        return value
    
    def validate_content(self, value):
        """Valider le contenu du post"""
        if len(value.strip()) < 5:
            raise serializers.ValidationError("Le contenu doit contenir au moins 5 caractères.")
        if len(value) > 2000:
            raise serializers.ValidationError("Le contenu ne peut pas dépasser 2000 caractères.")
        return value
    
    def create(self, validated_data):
        # Assigner l'utilisateur et définir le statut
        validated_data['user'] = self.context['request'].user
        
        # Si une date est planifiée, mettre le statut à SCHEDULED
        if validated_data.get('scheduled_time'):
            validated_data['status'] = PostStatus.SCHEDULED
        else:
            validated_data['status'] = PostStatus.DRAFT
            
        return super().create(validated_data)

class PostSerializer(serializers.ModelSerializer):
    """Serializer complet pour les posts"""
    user_email = serializers.CharField(source='user.email', read_only=True)
    is_scheduled = serializers.BooleanField(read_only=True)
    is_due = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Post
        fields = [
            'id', 'user_email', 'content', 'platforms', 
            'scheduled_time', 'status', 'image', 'video',
            'created_at', 'updated_at', 'published_at',
            'is_scheduled', 'is_due', 'error_message'
        ]
        read_only_fields = [
            'id', 'user_email', 'created_at', 'updated_at', 
            'published_at', 'is_scheduled', 'is_due',
            'celery_task_id', 'error_message'
        ]

class PostUpdateSerializer(serializers.ModelSerializer):
    """Serializer pour mettre à jour un post"""
    
    class Meta:
        model = Post
        fields = ['content', 'platforms', 'scheduled_time', 'image', 'video']
    
    def validate_scheduled_time(self, value):
        """Ne permettre la modification que si le post n'est pas encore publié"""
        if self.instance.status == PostStatus.PUBLISHED:
            raise serializers.ValidationError("Impossible de modifier un post déjà publié.")
        
        if value and value <= timezone.now():
            raise serializers.ValidationError("La date de planification doit être dans le futur.")
        
        return value
    
    def update(self, instance, validated_data):
        # Mettre à jour le statut selon la planification
        if 'scheduled_time' in validated_data:
            if validated_data['scheduled_time']:
                instance.status = PostStatus.SCHEDULED
            else:
                instance.status = PostStatus.DRAFT
        
        return super().update(instance, validated_data)