from django.db import models

from apps.common.models import TimeStampedModel


class StaticPage(TimeStampedModel):
    class Slug(models.TextChoices):
        PRIVACY_POLICY = "privacy-policy", "Privacy Policy"
        TERMS_OF_SERVICE = "terms-of-service", "Terms of Service"
        COOKIE_POLICY = "cookie-policy", "Cookie Policy"
        ABOUT_US = "about-us", "About Us"

    slug = models.CharField(max_length=32, choices=Slug.choices, unique=True)
    title = models.CharField(max_length=255)
    content = models.TextField()
    is_published = models.BooleanField(default=True)

    class Meta:
        db_table = "static_pages"
        ordering = ("slug",)

    def __str__(self) -> str:
        return self.title
