from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("seatgeek", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="events",
            index=models.Index(fields=["start_date"], name="ev_start_date_idx"),
        ),
        migrations.AddIndex(
            model_name="events",
            index=models.Index(fields=["end_date"], name="ev_end_date_idx"),
        ),
        migrations.AddIndex(
            model_name="events",
            index=models.Index(fields=["start_date", "end_date"], name="ev_start_end_idx"),
        ),
    ]
