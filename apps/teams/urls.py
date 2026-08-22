from django.urls import path
from . import views

app_name = "teams"

urlpatterns = [
    path("roles/", views.RoleHierarchyView.as_view(), name="role-hierarchy"),
    path("users/related/", views.RelatedUserSearchView.as_view(), name="related-user-search"),
    path("artists/related/", views.RelatedArtistSearchView.as_view(), name="related-artist-search"),
    path("users/", views.PublicUserSearchView.as_view(), name="public-user-search"),
    path("public/", views.PublicTeamSearchView.as_view(), name="public-team-search"),
    path("", views.TeamListCreateView.as_view(), name="team-list-create"),
    path("<int:team_id>/", views.TeamDetailView.as_view(), name="team-detail"),
    path(
        "<int:team_id>/members/",
        views.TeamMemberListCreateView.as_view(),
        name="member-list-create",
    ),
    path(
        "<int:team_id>/members/<int:membership_id>/",
        views.TeamMemberDetailView.as_view(),
        name="member-detail",
    ),
    path(
        "<int:team_id>/invitations/",
        views.TeamInvitationListCreateView.as_view(),
        name="invitation-list-create",
    ),
    path(
        "<int:team_id>/invitations/<int:invitation_id>/revoke/",
        views.TeamInvitationRevokeView.as_view(),
        name="invitation-revoke",
    ),
    path(
        "invitations/accept/",
        views.InvitationAcceptView.as_view(),
        name="invitation-accept",
    ),
    path(
        "invitations/decline/",
        views.InvitationDeclineView.as_view(),
        name="invitation-decline",
    ),
    # Superuser review queue
    path(
        "review/memberships/",
        views.MembershipReviewListView.as_view(),
        name="membership-review-list",
    ),
    path(
        "review/memberships/<int:membership_id>/",
        views.MembershipReviewDetailView.as_view(),
        name="membership-review-detail",
    ),
]
