from django.db import models

class Offer(models.Model):
    artist_name = models.CharField(max_length=128)
    date = models.DateField()
    venue = models.CharField(max_length=128)
    venue_address = models.CharField(max_length=256)
    city_state_country_zip = models.CharField(max_length=128)
    venue_phone = models.CharField(max_length=32)

    offer_amount = models.DecimalField(max_digits=10, decimal_places=2)
    expected_attendance = models.IntegerField()
    past_performers = models.CharField(max_length=256, null=True, blank=True)
    social_media_request = models.CharField(max_length=256, null=True, blank=True)
    what_is_event_for = models.CharField(max_length=256, null=True, blank=True)
    other_artists = models.CharField(max_length=256, null=True, blank=True)

    contact_signatory_name = models.CharField(max_length=128)
    contact_signatory_address = models.CharField(max_length=256)
    contact_signatory_contact_info = models.CharField(max_length=32)

    contact_buyer_name = models.CharField(max_length=128)
    contact_buyer_address = models.CharField(max_length=256)
    contact_buyer_contact_info = models.CharField(max_length=32)

    contact_production_name = models.CharField(max_length=128)
    contact_production_contact_info = models.CharField(max_length=32)

    additional_notes = models.TextField(null=True, blank=True)

    signature = models.ImageField(upload_to='offer_signatures/', null=True, blank=True)


class OfferDocument(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='documents')
    document = models.FileField(upload_to='offer_documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)



