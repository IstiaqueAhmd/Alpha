from django.urls import path

from .views import (
    ActivityFeedView,
    AvailabilityDeleteView,
    AvailabilityListView,
    BookingOfferAcceptView,
    BookingOfferListCreateView,
    BookingOfferRejectView,
    DashboardView,
    PublicArtistAvailabilityView,
    SendToUsersView,
)

app_name = "bookings"

urlpatterns = [
    path("availability/", AvailabilityListView.as_view(), name="availability"),
    path("availability/<str:slot_date>/", AvailabilityDeleteView.as_view(), name="availability-delete"),
    path("artists/<int:artist_id>/availability/", PublicArtistAvailabilityView.as_view(), name="artist-availability"),
    path("offers/", BookingOfferListCreateView.as_view(), name="offers"),
    path("offers/<int:offer_id>/accept/", BookingOfferAcceptView.as_view(), name="offer-accept"),
    path("offers/<int:offer_id>/reject/", BookingOfferRejectView.as_view(), name="offer-reject"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("activity/", ActivityFeedView.as_view(), name="activity"),
    path("send-to/", SendToUsersView.as_view(), name="send-to"),
]
