from django.db import models


class EventDownloaderProgresses(models.Model):
    id = models.CharField(primary_key=True, max_length=191)
    pages_processed = models.IntegerField()
    pages = models.IntegerField()
    page_size = models.IntegerField()
    provider_name = models.CharField(max_length=256)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = "event_downloader_progresses"


class Events(models.Model):
    id = models.CharField(primary_key=True, max_length=191)
    venue = models.ForeignKey("Venues", models.DO_NOTHING, blank=True, null=True)
    provider_name = models.CharField(max_length=256)
    provider_id = models.CharField(max_length=256)
    name = models.CharField(max_length=256)
    url = models.CharField(max_length=256)
    location_name = models.CharField(max_length=256)
    location_url = models.CharField(max_length=256)
    start_date = models.DateField()
    end_date = models.DateField()
    address = models.CharField(max_length=256)
    lat = models.FloatField(blank=True, null=True)
    long = models.FloatField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = "events"
        unique_together = (("provider_name", "provider_id"),)


class PerformerEvents(models.Model):
    id = models.CharField(primary_key=True, max_length=191)
    performer = models.ForeignKey("Performers", models.DO_NOTHING)
    event = models.ForeignKey(Events, models.DO_NOTHING)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = "performer_events"
        unique_together = (("performer", "event"),)


class PerformerGenres(models.Model):
    id = models.CharField(primary_key=True, max_length=191)
    performer = models.ForeignKey("Performers", models.DO_NOTHING)
    genre = models.TextField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = "performer_genres"
        unique_together = (("performer", "genre"),)


class PerformerScorerProgresses(models.Model):
    id = models.CharField(primary_key=True, max_length=191)
    last_processed_performer_id = models.CharField(max_length=256)
    completed = models.BooleanField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = "performer_scorer_progresses"


class PerformerSeatgeekGenres(models.Model):
    id = models.CharField(primary_key=True, max_length=191)
    performer = models.ForeignKey("Performers", models.DO_NOTHING)
    seatgeek_genre = models.ForeignKey("SeatgeekGenres", models.DO_NOTHING)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = "performer_seatgeek_genres"
        unique_together = (("performer", "seatgeek_genre"),)


class Performers(models.Model):
    id = models.CharField(primary_key=True, max_length=191)
    name = models.CharField(max_length=256)
    provider_id = models.CharField(max_length=256)
    provider_name = models.CharField(max_length=256)
    url = models.CharField(max_length=256)
    image = models.CharField(max_length=256)
    score = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = "performers"
        unique_together = (("provider_name", "provider_id"),)


class SeatgeekGenres(models.Model):
    id = models.CharField(primary_key=True, max_length=191)
    seatgeek_id = models.CharField(unique=True, max_length=256)
    name = models.CharField(max_length=256)
    slug = models.CharField(max_length=256)
    image = models.CharField(max_length=256, blank=True, null=True)
    primary = models.BooleanField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = "seatgeek_genres"


class Venues(models.Model):
    id = models.CharField(primary_key=True, max_length=191)
    provider_name = models.CharField(max_length=256)
    provider_id = models.CharField(max_length=256)
    provider_slug = models.CharField(max_length=256)
    provider_url = models.CharField(max_length=256)
    name = models.CharField(max_length=256)
    address = models.CharField(max_length=256)
    city = models.CharField(max_length=256)
    state = models.CharField(max_length=256)
    postal_code = models.CharField(max_length=256)
    country = models.CharField(max_length=256)
    lat = models.FloatField()
    long = models.FloatField()
    capacity = models.IntegerField()
    score = models.FloatField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = "venues"
        unique_together = (("provider_name", "provider_id"),)
