from django.conf import settings
from django.db import models
from django.utils.text import slugify

from apps.common.models import TimeStampedModel


class Category(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)

    class Meta:
        db_table = "blog_categories"
        ordering = ("name",)
        verbose_name_plural = "categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class Post(TimeStampedModel):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    content = models.TextField()
    image = models.ImageField(upload_to="blog_posts/", blank=True, null=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posts",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blog_posts",
    )
    is_published = models.BooleanField(default=True)

    class Meta:
        db_table = "blog_posts"
        ordering = ("-created_at",)

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:270]
            slug = base
            suffix = 1
            while Post.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                suffix += 1
                slug = f"{base}-{suffix}"
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.title
