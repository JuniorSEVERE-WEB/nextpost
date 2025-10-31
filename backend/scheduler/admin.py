from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Post, SocialAccount, PostMediaAsset

class PostMediaAssetInline(admin.TabularInline):
    """Inline admin for post media assets"""
    model = PostMediaAsset
    extra = 0
    readonly_fields = ('asset_preview', 'asset_info')
    fields = ('asset', 'asset_preview', 'asset_info', 'order', 'metadata')
    
    def asset_preview(self, obj):
        """Show thumbnail preview of media asset"""
        if obj.asset and obj.asset.is_image():
            thumbnail = obj.asset.get_thumbnail('small')
            if thumbnail:
                return format_html(
                    '<img src="{}" width="50" height="50" style="object-fit: cover;" />',
                    thumbnail
                )
        elif obj.asset:
            return format_html(
                '<div style="width: 50px; height: 50px; background: #f0f0f0; display: flex; align-items: center; justify-content: center; font-size: 12px;">{}</div>',
                obj.asset.media_type.upper()[:3] if obj.asset.media_type else 'FILE'
            )
        return "No preview"
    asset_preview.short_description = 'Preview'
    
    def asset_info(self, obj):
        """Show asset information"""
        if obj.asset:
            return format_html(
                '<div><strong>{}</strong><br/><small>{}</small></div>',
                obj.asset.original_filename,
                obj.asset.file_size_human
            )
        return "No asset"
    asset_info.short_description = 'Asset Info'

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'title', 'user', 'social_account', 'platform_display', 
        'status', 'validation_status', 'media_count', 'scheduled_time', 'created_at'
    )
    list_filter = (
        'status', 'is_active', 'social_account__platform', 
        'created_at', 'scheduled_time'
    )
    search_fields = ('title', 'content', 'user__email', 'social_account__username')
    readonly_fields = (
        'created_at', 'updated_at', 'published_at', 'platform_post_id',
        'validation_preview', 'platform_rules_preview'
    )
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'title', 'content', 'social_account', 'is_active')
        }),
        ('Scheduling', {
            'fields': ('status', 'scheduled_time', 'published_at')
        }),
        ('Platform Configuration', {
            'fields': ('platform_configs', 'validation_preview', 'platform_rules_preview'),
            'classes': ('collapse',)
        }),
        ('Legacy Media (Deprecated)', {
            'fields': ('image', 'video'),
            'classes': ('collapse',),
            'description': 'These fields are deprecated. Use Media Assets instead.'
        }),
        ('Publishing Info', {
            'fields': ('platform_post_id', 'error_message'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    inlines = [PostMediaAssetInline]
    
    def platform_display(self, obj):
        """Display platform with icon"""
        if obj.social_account:
            platform_icons = {
                'facebook_page': '📘',
                'facebook_group': '👥',
                'instagram_feed': '📷',
                'instagram_story': '📖',
                'instagram_reels': '🎬',
                'twitter': '🐦',
                'linkedin_page': '💼',
                'linkedin_personal': '👤',
                'tiktok': '🎵',
                'youtube': '📺'
            }
            icon = platform_icons.get(obj.social_account.platform, '📱')
            return format_html(
                '{} {}',
                icon,
                obj.social_account.get_platform_display()
            )
        return "No platform"
    platform_display.short_description = 'Platform'
    
    def validation_status(self, obj):
        """Show validation status with color coding"""
        try:
            errors = obj.validate_for_platform()
            if not errors:
                return format_html(
                    '<span style="color: green; font-weight: bold;">✓ Valid</span>'
                )
            else:
                return format_html(
                    '<span style="color: red; font-weight: bold;">✗ {} errors</span>',
                    len(errors)
                )
        except Exception:
            return format_html(
                '<span style="color: orange; font-weight: bold;">? Unknown</span>'
            )
    validation_status.short_description = 'Validation'
    
    def media_count(self, obj):
        """Show number of attached media assets"""
        count = obj.postmediaasset_set.count()
        if count > 0:
            return format_html(
                '<span style="background: #e1f5fe; padding: 2px 6px; border-radius: 3px;">{} assets</span>',
                count
            )
        return "No media"
    media_count.short_description = 'Media'
    
    def validation_preview(self, obj):
        """Show validation errors in admin"""
        try:
            errors = obj.validate_for_platform()
            if not errors:
                return mark_safe('<span style="color: green;">✓ Post is valid for this platform</span>')
            else:
                error_list = ''.join([f'<li>{error}</li>' for error in errors])
                return mark_safe(f'<ul style="color: red;">{error_list}</ul>')
        except Exception as e:
            return mark_safe(f'<span style="color: orange;">Validation error: {str(e)}</span>')
    validation_preview.short_description = 'Validation Status'
    
    def platform_rules_preview(self, obj):
        """Show platform rules in admin"""
        try:
            rules = obj.get_platform_rules()
            rules_html = []
            for key, value in rules.items():
                rules_html.append(f'<strong>{key.replace("_", " ").title()}:</strong> {value}')
            return mark_safe('<br/>'.join(rules_html))
        except Exception:
            return "Rules not available"
    platform_rules_preview.short_description = 'Platform Rules'

@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'platform_display', 'username', 'is_active', 
        'posts_count', 'last_used_display', 'created_at'
    )
    list_filter = ('platform', 'is_active', 'created_at', 'last_used_at')
    search_fields = ('username', 'user__email')
    readonly_fields = (
        'created_at', 'updated_at', 'posts_count', 'last_used_at',
        'platform_capabilities_preview'
    )
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'platform', 'username', 'is_active')
        }),
        ('Platform Configuration', {
            'fields': ('platform_config', 'platform_capabilities_preview'),
            'classes': ('collapse',)
        }),
        ('Usage Statistics', {
            'fields': ('posts_count', 'last_used_at'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def platform_display(self, obj):
        """Display platform with icon"""
        platform_icons = {
            'facebook_page': '📘',
            'facebook_group': '👥',
            'instagram_feed': '📷',
            'instagram_story': '📖',
            'instagram_reels': '🎬',
            'twitter': '🐦',
            'linkedin_page': '💼',
            'linkedin_personal': '👤',
            'tiktok': '🎵',
            'youtube': '📺'
        }
        icon = platform_icons.get(obj.platform, '📱')
        return format_html(
            '{} {}',
            icon,
            obj.get_platform_display()
        )
    platform_display.short_description = 'Platform'
    
    def last_used_display(self, obj):
        """Display last used time in a friendly format"""
        if obj.last_used_at:
            return obj.last_used_at.strftime('%Y-%m-%d %H:%M')
        return "Never used"
    last_used_display.short_description = 'Last Used'
    
    def platform_capabilities_preview(self, obj):
        """Show platform capabilities in admin"""
        try:
            capabilities = obj.get_platform_capabilities()
            caps_html = []
            for key, value in capabilities.items():
                if isinstance(value, dict):
                    caps_html.append(f'<strong>{key.replace("_", " ").title()}:</strong>')
                    for sub_key, sub_value in value.items():
                        caps_html.append(f'&nbsp;&nbsp;{sub_key.replace("_", " ").title()}: {sub_value}')
                else:
                    caps_html.append(f'<strong>{key.replace("_", " ").title()}:</strong> {value}')
            return mark_safe('<br/>'.join(caps_html))
        except Exception:
            return "Capabilities not available"
    platform_capabilities_preview.short_description = 'Platform Capabilities'

@admin.register(PostMediaAsset)
class PostMediaAssetAdmin(admin.ModelAdmin):
    list_display = ('id', 'post', 'asset_preview', 'asset_name', 'order', 'created_at')
    list_filter = ('asset__media_type', 'created_at')
    search_fields = ('post__title', 'post__content', 'asset__original_filename')
    readonly_fields = ('created_at', 'asset_preview', 'asset_details')
    
    def asset_preview(self, obj):
        """Show asset preview"""
        if obj.asset and obj.asset.is_image():
            thumbnail = obj.asset.get_thumbnail('small')
            if thumbnail:
                return format_html(
                    '<img src="{}" width="100" height="100" style="object-fit: cover;" />',
                    thumbnail
                )
        return "No preview"
    asset_preview.short_description = 'Preview'
    
    def asset_name(self, obj):
        """Show asset name"""
        return obj.asset.original_filename if obj.asset else "No asset"
    asset_name.short_description = 'Asset Name'
    
    def asset_details(self, obj):
        """Show detailed asset information"""
        if obj.asset:
            return format_html(
                '<strong>Filename:</strong> {}<br/>'
                '<strong>Size:</strong> {}<br/>'
                '<strong>Type:</strong> {}<br/>'
                '<strong>Hash:</strong> {}',
                obj.asset.original_filename,
                obj.asset.file_size_human,
                obj.asset.media_type,
                obj.asset.sha256_hash[:16] + '...' if obj.asset.sha256_hash else 'N/A'
            )
        return "No asset information"
    asset_details.short_description = 'Asset Details'
