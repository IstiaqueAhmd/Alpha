from django.contrib import admin

from .models import AvailDate, AvailEntry, AvailList, AvailShare


class AvailEntryInline(admin.TabularInline):
    model = AvailEntry
    extra = 0
    fields = ("artist", "genre", "location", "position")
    raw_id_fields = ("artist",)


class AvailShareInline(admin.TabularInline):
    model = AvailShare
    extra = 0
    fields = ("shared_with", "shared_email", "message")
    raw_id_fields = ("shared_with",)


@admin.register(AvailList)
class AvailListAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "visibility", "created_at")
    list_filter = ("visibility",)
    search_fields = ("name", "owner__email")
    raw_id_fields = ("owner",)
    inlines = [AvailEntryInline, AvailShareInline]


class AvailDateInline(admin.TabularInline):
    model = AvailDate
    extra = 0


@admin.register(AvailEntry)
class AvailEntryAdmin(admin.ModelAdmin):
    list_display = ("avail_list", "artist", "genre", "position", "created_at")
    search_fields = ("artist__name", "artist__email", "genre")
    raw_id_fields = ("avail_list", "artist")
    inlines = [AvailDateInline]


@admin.register(AvailShare)
class AvailShareAdmin(admin.ModelAdmin):
    list_display = ("avail_list", "shared_by", "shared_with", "shared_email", "created_at")
    search_fields = ("shared_email", "shared_with__email")
    raw_id_fields = ("avail_list", "shared_by", "shared_with")
