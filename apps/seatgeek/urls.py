from django.urls import path
from . import views

app_name = "seatgeek"

urlpatterns = [
    path("performers/", views.PerformerSearchView.as_view(), name="performer-search"),
]
