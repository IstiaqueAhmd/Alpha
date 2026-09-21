from django.urls import path

from . import views

app_name = "artist_claims"

urlpatterns = [
    path("search/", views.ClaimedArtistSearchView.as_view(), name="claimed-artist-search"),
    path("", views.ArtistClaimListCreateView.as_view(), name="claim-list-create"),
    path("<int:claim_id>/", views.ArtistClaimDetailView.as_view(), name="claim-detail"),
    path("review/", views.ClaimReviewListView.as_view(), name="claim-review-list"),
    path("review/<int:claim_id>/", views.ClaimReviewDetailView.as_view(), name="claim-review-detail"),
]
