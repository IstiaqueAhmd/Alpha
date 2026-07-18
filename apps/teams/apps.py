from django.apps import AppConfig


class TeamsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.teams"
    verbose_name = "Teams"

    def ready(self):
        # Connect the post_save receiver that auto-enrolls verified users.
        from . import signals
