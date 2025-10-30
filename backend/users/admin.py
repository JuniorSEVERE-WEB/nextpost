from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import User

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Infos perso", {"fields": ("full_name", "avatar")}),
        ("Permissions", {"fields": ("is_active","is_staff","is_superuser","groups","user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )
    list_display = ("id","email","full_name","is_staff","is_active")
    search_fields = ("email","full_name")
    ordering = ("-id",)
