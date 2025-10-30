from django.contrib import admin
from .models import Post, SocialAccount

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'content_preview', 'status', 'scheduled_time', 'created_at')
    list_filter = ('status', 'platforms', 'created_at')
    search_fields = ('content', 'user__email')
    readonly_fields = ('created_at', 'updated_at', 'published_at', 'celery_task_id')
    
    def content_preview(self, obj):
        return obj.content[:50] + "..." if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Contenu'

@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'platform', 'username', 'is_active', 'created_at')
    list_filter = ('platform', 'is_active', 'created_at')
    search_fields = ('username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
