from django.urls import path

from .views import InquiryListCreateView

app_name = "inquiries"

urlpatterns = [
    path("", InquiryListCreateView.as_view(), name="inquiries"),
]
