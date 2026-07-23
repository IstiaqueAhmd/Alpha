from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, PostViewSet

app_name = "blog"

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("posts", PostViewSet, basename="post")

urlpatterns = router.urls
