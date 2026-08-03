from django.urls import path

from .views import (
    OfferAcceptView,
    OfferDetailView,
    OfferDocumentUploadView,
    OfferListCreateView,
    OfferRejectView,
    OfferShareView,
    OfferSignView,
)

app_name = "offers"

urlpatterns = [
    path("", OfferListCreateView.as_view(), name="offers"),
    path("<int:offer_id>/", OfferDetailView.as_view(), name="offer-detail"),
    path("<int:offer_id>/accept/", OfferAcceptView.as_view(), name="offer-accept"),
    path("<int:offer_id>/reject/", OfferRejectView.as_view(), name="offer-reject"),
    path("<int:offer_id>/share/", OfferShareView.as_view(), name="offer-share"),
    path("<int:offer_id>/sign/", OfferSignView.as_view(), name="offer-sign"),
    path("<int:offer_id>/documents/", OfferDocumentUploadView.as_view(), name="offer-documents"),
]
