from django.contrib import admin

from .models import Category, Post


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "category", "author", "is_published", "created_at")
    list_filter = ("is_published", "category")
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
