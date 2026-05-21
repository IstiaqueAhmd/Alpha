import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("seatgeek", "0002_event_date_indexes"),
        ("bookings", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="bookingoffer",
            name="artist",
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={"role": "artist"},
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="received_offers",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="bookingoffer",
            name="seatgeek_performer",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="received_offers",
                to="seatgeek.performers",
            ),
        ),
        migrations.AddIndex(
            model_name="bookingoffer",
            index=models.Index(
                fields=["seatgeek_performer", "status", "-event_date"],
                name="booking_off_seatgee_6163a6_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="bookingoffer",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(("artist__isnull", False), ("seatgeek_performer__isnull", True))
                    | models.Q(("artist__isnull", True), ("seatgeek_performer__isnull", False))
                ),
                name="booking_offer_artist_xor_seatgeek",
            ),
        ),
    ]
