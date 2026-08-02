from django.urls import path

from .views import (
    InquiryAcceptView,
    InquiryDeclineView,
    InquiryDetailView,
    InquiryListCreateView,
)

app_name = "inquiries"

urlpatterns = [
    path("", InquiryListCreateView.as_view(), name="inquiries"),
    path("<int:inquiry_id>/", InquiryDetailView.as_view(), name="inquiry-detail"),
    path("<int:inquiry_id>/accept/", InquiryAcceptView.as_view(), name="inquiry-accept"),
    path("<int:inquiry_id>/decline/", InquiryDeclineView.as_view(), name="inquiry-decline"),
]
