from django.urls import path

from . import views

app_name = "avails"

urlpatterns = [
    # Lists
    path("", views.AvailListView.as_view(), name="list-create"),
    path("shared/", views.AvailListSharedView.as_view(), name="shared-with-me"),
    path("sent/", views.AvailListSentView.as_view(), name="sent"),
    path("public/", views.AvailListPublicView.as_view(), name="public"),
    path("<int:list_id>/", views.AvailListDetailView.as_view(), name="detail"),
    # Entries (artists in a list)
    path(
        "<int:list_id>/entries/",
        views.AvailEntryListCreateView.as_view(),
        name="entry-list-create",
    ),
    path(
        "<int:list_id>/entries/<int:entry_id>/",
        views.AvailEntryDetailView.as_view(),
        name="entry-detail",
    ),
    path(
        "<int:list_id>/entries/<int:entry_id>/dates/",
        views.AvailEntryDatesView.as_view(),
        name="entry-dates",
    ),
    # Sharing
    path(
        "<int:list_id>/shares/",
        views.AvailShareListCreateView.as_view(),
        name="share-list-create",
    ),
    path(
        "<int:list_id>/shares/<int:share_id>/",
        views.AvailShareDetailView.as_view(),
        name="share-detail",
    ),
]
