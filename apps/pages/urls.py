from rest_framework.routers import DefaultRouter

from .views import StaticPageViewSet

app_name = "pages"

router = DefaultRouter()
router.register("", StaticPageViewSet, basename="page")

urlpatterns = router.urls
