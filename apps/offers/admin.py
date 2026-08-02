from django.contrib import admin

from .models import Offer, OfferDocument, OfferSignature

admin.site.register(Offer)
admin.site.register(OfferSignature)
admin.site.register(OfferDocument)
