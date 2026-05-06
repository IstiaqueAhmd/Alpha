import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()


class Command(BaseCommand):
    help = "Create a staff admin user (already email-verified, ready to log in)."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--name", required=True)
        parser.add_argument(
            "--role",
            default=User.Role.ORGANIZER,
            choices=[r for r, _ in User.Role.choices],
            help="Account role (default: organizer).",
        )
        parser.add_argument("--superuser", action="store_true")
        parser.add_argument(
            "--password",
            default=None,
            help="If omitted, you will be prompted securely.",
        )

    def handle(self, *args, **options):
        email = options["email"].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError(f"User with email {email} already exists.")

        password = options["password"] or getpass.getpass("Password: ")
        if not password:
            raise CommandError("Password cannot be empty.")

        kwargs = {
            "name": options["name"],
            "role": options["role"],
            "is_staff": True,
            "is_active": True,
        }

        if options["superuser"]:
            user = User.objects.create_superuser(email=email, password=password, **kwargs)
        else:
            user = User.objects.create_user(email=email, password=password, **kwargs)
            # Mark email as verified so the admin can log in immediately.
            user.mark_email_verified()

        self.stdout.write(
            self.style.SUCCESS(
                f"Created admin user: {user.email} (id={user.pk}, role={user.role}, "
                f"superuser={user.is_superuser})"
            )
        )
