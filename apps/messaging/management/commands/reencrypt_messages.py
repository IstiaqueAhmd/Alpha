import time

from django.core.management.base import BaseCommand, CommandError

from apps.messaging.models import Message


class Command(BaseCommand):
    """Re-encrypts every Message.body onto the active MESSAGE_ENCRYPTION_KEYS[0].

    Run this after rotating keys (new key prepended to MESSAGE_ENCRYPTION_KEYS,
    old key kept in the list so old rows still decrypt). A plain `.save()`
    already does the work - EncryptedTextField decrypts on load with
    whichever configured key matches, and re-encrypts on save with the
    current active key - this command just walks every row in batches so it
    can run against millions of rows without loading them all into memory.

    Safe to stop and re-run: it re-encrypts rows unconditionally rather than
    tracking a "done" flag, so a repeat run over already-migrated rows is a
    no-op change (same active key both times). Use --start-id to skip ahead
    after an interrupted run instead of re-walking from the beginning.
    """

    help = "Re-encrypt all message bodies onto the active MESSAGE_ENCRYPTION_KEYS[0] entry."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=2000)
        parser.add_argument("--start-id", type=int, default=0, help="Resume after this message id.")
        parser.add_argument("--sleep", type=float, default=0, help="Seconds to sleep between batches.")

    def handle(self, *args, **options):
        from django.conf import settings

        if not settings.MESSAGE_ENCRYPTION_KEYS:
            raise CommandError("MESSAGE_ENCRYPTION_KEYS is empty - nothing to encrypt with.")

        batch_size = options["batch_size"]
        last_id = options["start_id"]
        sleep_seconds = options["sleep"]
        total = 0

        while True:
            batch = list(
                Message.objects.filter(id__gt=last_id).order_by("id")[:batch_size]
            )
            if not batch:
                break

            for message in batch:
                # .body was decrypted on load above; re-assigning it and
                # saving re-runs get_prep_value, which encrypts with the
                # current active key.
                message.save(update_fields=["body"])

            last_id = batch[-1].pk
            total += len(batch)
            self.stdout.write(f"Re-encrypted up to id={last_id} ({total} total)")

            if sleep_seconds:
                time.sleep(sleep_seconds)

        self.stdout.write(self.style.SUCCESS(f"Done. Re-encrypted {total} messages."))
