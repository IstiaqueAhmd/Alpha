from django.contrib import admin

from .models import Team, TeamInvitation, TeamMembership


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "domain", "status", "created_by", "created_at")
    list_filter = ("domain", "status")
    search_fields = ("name", "created_by__email")
    raw_id_fields = ("created_by", "approved_by")


@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "team", "role", "status", "created_at")
    list_filter = ("status", "role")
    search_fields = ("user__email", "team__name")
    raw_id_fields = ("team", "user", "invited_by", "approved_by")


@admin.register(TeamInvitation)
class TeamInvitationAdmin(admin.ModelAdmin):
    list_display = ("email", "team", "role", "status", "expires_at", "created_at")
    list_filter = ("status", "role")
    search_fields = ("email", "team__name")
    raw_id_fields = ("team", "invited_by", "accepted_by")
    # The token redeems the invite - readable in admin, never editable.
    readonly_fields = ("token",)
