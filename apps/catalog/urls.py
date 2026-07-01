from django.urls import path

from .views import (
    ArtistDetailView,
    ArtistListView,
    FavoriteDeleteView,
    FavoriteShareView,
    FavoritesView,
    GenreListView,
    MyArtistProfileView,
    MyVenueProfileView,
    RecentSearchesView,
    SharedFavoritesView,
    SharedVenueFavoritesView,
    VenueDetailView,
    VenueFavoriteDeleteView,
    VenueFavoriteShareView,
    VenueFavoritesView,
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
    path("favorites/artist/", FavoritesView.as_view(), name="favorites-artist"),
    path("favorites/artist/share/", FavoriteShareView.as_view(), name="favorites-share"),
    path("favorites/artist/shared/<str:token>/", SharedFavoritesView.as_view(), name="favorites-shared"),
    path("favorites/artist/<str:artist_id>/", FavoriteDeleteView.as_view(), name="favorite-delete"),
    path("favorites/venue/", VenueFavoritesView.as_view(), name="favorites-venue"),
    path("favorites/venue/share/", VenueFavoriteShareView.as_view(), name="favorites-venue-share"),
    path("favorites/venue/shared/<str:token>/", SharedVenueFavoritesView.as_view(), name="favorites-venue-shared"),
    path("favorites/venue/<str:venue_id>/", VenueFavoriteDeleteView.as_view(), name="favorite-venue-delete"),
    path("recent-searches/", RecentSearchesView.as_view(), name="recent-searches"),
]

