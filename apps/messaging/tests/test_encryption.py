from cryptography.fernet import Fernet, InvalidToken
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings

from apps.messaging.models import Conversation, ConversationMember, Message
from apps.messaging.services import ConversationService, MessageService

User = get_user_model()

KEY_A = Fernet.generate_key().decode()
KEY_B = Fernet.generate_key().decode()


def make_user(email: str) -> User:
    return User.objects.create_user(email=email, name=email.split("@")[0], password="pass12345")


def raw_body(message_id: int) -> str:
    """Bypasses the ORM (and therefore EncryptedTextField.from_db_value) to
    read exactly what's stored in the column, the way a DB dump would see it.
    """
    with connection.cursor() as cur:
        cur.execute("SELECT body FROM messages WHERE id = %s", [message_id])
        return cur.fetchone()[0]


class EncryptionAtRestTests(TestCase):
    """MESSAGE_ENCRYPTION_KEYS=[KEY_A] - the normal "encryption is on" case."""

    def setUp(self):
        self.alice = make_user("enc-alice@example.com")
        self.bob = make_user("enc-bob@example.com")
        self.conversation, _ = ConversationService.get_or_create_direct(
            viewer=self.alice, other_user_id=self.bob.pk,
        )

    @override_settings(MESSAGE_ENCRYPTION_KEYS=[KEY_A])
    def test_body_is_not_plaintext_in_the_database(self):
        message = MessageService.send(viewer=self.alice, conversation=self.conversation, body="hello secret world")
        stored = raw_body(message.pk)
        self.assertNotIn("hello secret world", stored)
        self.assertTrue(stored.startswith("gAAAAA"))  # Fernet token prefix

    @override_settings(MESSAGE_ENCRYPTION_KEYS=[KEY_A])
    def test_orm_read_transparently_decrypts(self):
        message = MessageService.send(viewer=self.alice, conversation=self.conversation, body="hello secret world")
        message.refresh_from_db()
        self.assertEqual(message.body, "hello secret world")

    @override_settings(MESSAGE_ENCRYPTION_KEYS=[])
    def test_no_key_configured_falls_back_to_plaintext(self):
        message = MessageService.send(viewer=self.alice, conversation=self.conversation, body="no key yet")
        self.assertEqual(raw_body(message.pk), "no key yet")
        message.refresh_from_db()
        self.assertEqual(message.body, "no key yet")


class ExistingPlaintextMessageTests(TestCase):
    """Simulates the real migration case: messages sent while
    MESSAGE_ENCRYPTION_KEYS was unset (the app's whole life so far), then a
    key gets configured for the first time. Nothing should break, and
    nothing should require a data migration to become readable.
    """

    def setUp(self):
        self.alice = make_user("legacy-alice@example.com")
        self.bob = make_user("legacy-bob@example.com")
        self.conversation, _ = ConversationService.get_or_create_direct(
            viewer=self.alice, other_user_id=self.bob.pk,
        )
        with override_settings(MESSAGE_ENCRYPTION_KEYS=[]):
            self.legacy_message = MessageService.send(
                viewer=self.alice, conversation=self.conversation, body="written before any key existed",
            )
        self.assertEqual(raw_body(self.legacy_message.pk), "written before any key existed")

    @override_settings(MESSAGE_ENCRYPTION_KEYS=[KEY_A])
    def test_legacy_plaintext_message_still_reads_correctly_once_a_key_is_turned_on(self):
        self.legacy_message.refresh_from_db()
        self.assertEqual(self.legacy_message.body, "written before any key existed")

    @override_settings(MESSAGE_ENCRYPTION_KEYS=[KEY_A])
    def test_legacy_message_stays_plaintext_in_db_until_touched(self):
        # Turning the key on doesn't retroactively encrypt old rows by itself.
        Message.objects.get(pk=self.legacy_message.pk)  # a plain read, no save
        self.assertEqual(raw_body(self.legacy_message.pk), "written before any key existed")

    @override_settings(MESSAGE_ENCRYPTION_KEYS=[KEY_A])
    def test_editing_a_legacy_message_encrypts_it(self):
        MessageService.edit(viewer=self.alice, message=self.legacy_message, body="written before any key existed")
        stored = raw_body(self.legacy_message.pk)
        self.assertNotIn("written before any key existed", stored)

    @override_settings(MESSAGE_ENCRYPTION_KEYS=[KEY_A])
    def test_reencrypt_command_migrates_legacy_plaintext_rows(self):
        call_command("reencrypt_messages")
        stored = raw_body(self.legacy_message.pk)
        self.assertNotIn("written before any key existed", stored)
        self.legacy_message.refresh_from_db()
        self.assertEqual(self.legacy_message.body, "written before any key existed")


class KeyRotationTests(TestCase):
    def setUp(self):
        self.alice = make_user("rot-alice@example.com")
        self.bob = make_user("rot-bob@example.com")
        self.conversation, _ = ConversationService.get_or_create_direct(
            viewer=self.alice, other_user_id=self.bob.pk,
        )
        with override_settings(MESSAGE_ENCRYPTION_KEYS=[KEY_A]):
            self.message = MessageService.send(viewer=self.alice, conversation=self.conversation, body="rotate me")

    @override_settings(MESSAGE_ENCRYPTION_KEYS=[KEY_B, KEY_A])
    def test_old_key_row_still_readable_with_new_key_first_and_old_key_kept(self):
        self.message.refresh_from_db()
        self.assertEqual(self.message.body, "rotate me")

    @override_settings(MESSAGE_ENCRYPTION_KEYS=[KEY_B])
    def test_old_key_row_unreadable_once_old_key_is_dropped(self):
        # Passthrough-on-failure means this returns ciphertext garbage, not
        # a crash - but it does NOT recover the original text.
        self.message.refresh_from_db()
        self.assertNotEqual(self.message.body, "rotate me")

    @override_settings(MESSAGE_ENCRYPTION_KEYS=[KEY_B, KEY_A])
    def test_new_writes_use_the_new_active_key_immediately(self):
        second = MessageService.send(viewer=self.bob, conversation=self.conversation, body="written after rotation")
        stored = raw_body(second.pk)
        with self.assertRaises(InvalidToken):
            Fernet(KEY_A.encode()).decrypt(stored.encode())
        self.assertEqual(Fernet(KEY_B.encode()).decrypt(stored.encode()).decode(), "written after rotation")

    @override_settings(MESSAGE_ENCRYPTION_KEYS=[KEY_B, KEY_A])
    def test_full_rotation_cycle_old_key_can_be_dropped_after_reencrypt(self):
        call_command("reencrypt_messages")
        stored = raw_body(self.message.pk)

        # No longer decryptable with the retired key...
        with self.assertRaises(InvalidToken):
            Fernet(KEY_A.encode()).decrypt(stored.encode())

        # ...but fine under the new key alone, i.e. safe to drop KEY_A now.
        with override_settings(MESSAGE_ENCRYPTION_KEYS=[KEY_B]):
            self.message.refresh_from_db()
            self.assertEqual(self.message.body, "rotate me")

    @override_settings(MESSAGE_ENCRYPTION_KEYS=[KEY_B, KEY_A])
    def test_reencrypt_command_is_idempotent(self):
        call_command("reencrypt_messages")
        first_pass = raw_body(self.message.pk)
        call_command("reencrypt_messages")
        second_pass = raw_body(self.message.pk)
        self.assertEqual(
            Fernet(KEY_B.encode()).decrypt(first_pass.encode()),
            Fernet(KEY_B.encode()).decrypt(second_pass.encode()),
        )


class ReencryptCommandResumeTests(TestCase):
    @override_settings(MESSAGE_ENCRYPTION_KEYS=[KEY_A])
    def test_start_id_skips_already_processed_rows(self):
        alice = make_user("resume-alice@example.com")
        bob = make_user("resume-bob@example.com")
        conversation, _ = ConversationService.get_or_create_direct(viewer=alice, other_user_id=bob.pk)

        with override_settings(MESSAGE_ENCRYPTION_KEYS=[]):
            first = MessageService.send(viewer=alice, conversation=conversation, body="first")
            second = MessageService.send(viewer=alice, conversation=conversation, body="second")

        call_command("reencrypt_messages", start_id=first.pk)

        # first.pk was skipped (start_id is exclusive), still plaintext.
        self.assertEqual(raw_body(first.pk), "first")
        # second.pk was processed, now ciphertext.
        self.assertNotIn("second", raw_body(second.pk))
