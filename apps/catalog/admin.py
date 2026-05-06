from django.contrib import admin

from .models import ArtistProfile, Favorite, Genre, RecentSearch, VenueProfile


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ArtistProfile)
class ArtistProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "location", "experience_years", "base_price_cents", "is_published", "created_at")
    list_filter = ("is_published", "genres")
    search_fields = ("user__email", "user__name", "location")
    autocomplete_fields = ("user",)
    filter_horizontal = ("genres",)


@admin.register(VenueProfile)
class VenueProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "location", "capacity", "is_published", "created_at")
    list_filter = ("is_published",)
    search_fields = ("user__email", "user__name", "location", "address")
    autocomplete_fields = ("user",)


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("user", "artist", "created_at")
    search_fields = ("user__email", "artist__user__email")


@admin.register(RecentSearch)
class RecentSearchAdmin(admin.ModelAdmin):
    list_display = ("user", "query", "location", "target_date", "created_at")
    search_fields = ("user__email", "query", "location")
