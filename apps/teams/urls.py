from django.urls import path
from . import views

app_name = "teams"

urlpatterns = [
    path("roles/", views.RoleHierarchyView.as_view(), name="role-hierarchy"),
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
