import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.exceptions import NotFound, ValidationError

from apps.messaging.models import Message
from apps.messaging.services import ConversationService
from apps.offers.models import Offer
from apps.offers.services import OfferService

User = get_user_model()


def make_user(email: str, **kwargs) -> User:
    return User.objects.create_user(email=email, name=email.split("@")[0], password="pass12345", **kwargs)


def contract_fields(**overrides) -> dict:
    fields = dict(
        artist_name="The Roadrunners",
        date=datetime.date(2026, 6, 1),
        venue="The Venue",
        venue_address="1 Main St",
        city_state_country_zip="Springfield, IL, USA, 00000",
        venue_phone="555-0100",
        offer_amount=1000,
        door_time=datetime.time(20, 0),
        expected_attendance=200,
        contact_signatory_name="Sig Natory",
        contact_signatory_address="1 Sig St",
        contact_signatory_contact_info="555-0101",
        contact_buyer_name="Buyer Name",
        contact_buyer_address="1 Buyer St",
        contact_buyer_contact_info="555-0102",
        contact_production_name="Prod Name",
        contact_production_contact_info="555-0103",
    )
    fields.update(overrides)
    return fields


class ChatOfferTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice@example.com")
        self.bob = make_user("bob@example.com")
        self.carol = make_user("carol@example.com")
        self.dm, _ = ConversationService.get_or_create_direct(viewer=self.alice, other_user_id=self.bob.pk)

    def test_create_without_conversation_id_does_not_touch_chat(self):
        offer = OfferService.create(sender=self.alice, receiver_id=self.bob.pk, **contract_fields())
        self.assertFalse(Message.objects.filter(offer=offer).exists())

    def test_create_with_conversation_id_posts_a_chat_bubble(self):
        offer = OfferService.create(
            sender=self.alice, receiver_id=self.bob.pk, conversation_id=self.dm.pk, **contract_fields(),
        )
        message = Message.objects.get(offer=offer)

        self.assertEqual(message.kind, Message.Kind.OFFER)
        self.assertEqual(message.conversation_id, self.dm.pk)
        self.assertEqual(message.sender_id, self.alice.pk)

        conversation = ConversationService.get_for_viewer(self.alice, self.dm.pk)
        self.assertEqual(conversation.last_message_id, message.pk)

    def test_conversation_id_must_be_a_direct_conversation(self):
        group = ConversationService.create_group(viewer=self.alice, name="Crew", member_ids=[self.bob.pk, self.carol.pk])
        with self.assertRaises(ValidationError):
            OfferService.create(
                sender=self.alice, receiver_id=self.bob.pk, conversation_id=group.pk, **contract_fields(),
            )
        self.assertFalse(Offer.objects.exists())

    def test_conversation_id_receiver_mismatch_is_rejected(self):
        with self.assertRaises(ValidationError):
            OfferService.create(
                sender=self.alice, receiver_id=self.carol.pk, conversation_id=self.dm.pk, **contract_fields(),
            )
        self.assertFalse(Offer.objects.exists())

    def test_sender_not_in_conversation_is_rejected(self):
        other_dm, _ = ConversationService.get_or_create_direct(viewer=self.bob, other_user_id=self.carol.pk)
        with self.assertRaises(NotFound):
            OfferService.create(
                sender=self.alice, receiver_id=self.bob.pk, conversation_id=other_dm.pk, **contract_fields(),
            )
        self.assertFalse(Offer.objects.exists())
