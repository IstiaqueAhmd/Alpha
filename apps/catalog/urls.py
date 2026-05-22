from django.urls import path

from .views import (
    ArtistDetailView,
    ArtistListView,
    FavoriteDeleteView,
    FavoritesView,
    GenreListView,
    MyArtistProfileView,
    MyVenueProfileView,
    RecentSearchesView,
    VenueDetailView,
    VenueListView,
)

app_name = "catalog"

urlpatterns = [
    path("genres/", GenreListView.as_view(), name="genres"),
    path("artists/", ArtistListView.as_view(), name="artists-list"),
    path("artists/me/", MyArtistProfileView.as_view(), name="artist-me"),
    path("artists/<str:artist_id>/", ArtistDetailView.as_view(), name="artist-detail"),
    path("venues/", VenueListView.as_view(), name="venues-list"),
    path("venues/me/", MyVenueProfileView.as_view(), name="venue-me"),
    path("venues/<str:venue_id>/", VenueDetailView.as_view(), name="venue-detail"),
    path("favorites/", FavoritesView.as_view(), name="favorites"),
    path("favorites/<str:artist_id>/", FavoriteDeleteView.as_view(), name="favorite-delete"),
    path("recent-searches/", RecentSearchesView.as_view(), name="recent-searches"),
]
