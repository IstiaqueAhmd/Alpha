# Message body encryption

`Message.body` is encrypted at rest using `apps.messaging.crypto.EncryptedTextField`
(Fernet, via the `cryptography` package). Encryption/decryption is transparent
at the ORM level - services, serializers, and views read/write `message.body`
as a normal string. Nothing outside `apps/messaging/crypto.py` and
`apps/messaging/models.py` needed to change.

## How it works

- `MESSAGE_ENCRYPTION_KEYS` (settings, sourced from the env var of the same
  name) is a comma-separated list of Fernet keys.
- **Index 0** is the *active* key - every write (`Message.objects.create(...)`,
  `message.save()`) encrypts with it.
- **Every key in the list** is tried, in order, when decrypting
  (`cryptography.fernet.MultiFernet`). This is what makes rotation possible:
  an old message stays readable as long as the key it was encrypted with is
  still somewhere in the list, even after a newer key has taken index 0.
- If `MESSAGE_ENCRYPTION_KEYS` is empty, the field is a plain passthrough
  (no encryption) - lets local dev run with nothing configured.
- A value that fails to decrypt under every configured key is returned
  as-is rather than raising. This covers rows written before encryption was
  enabled on an existing deployment - they stay plaintext until touched by
  `reencrypt_messages` (or any other save), rather than breaking on read.

## Generating a key

```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Rotating a key

Rotate whenever a key may have leaked, or on a routine schedule. Rotating
does **not** protect data already encrypted under a leaked key - anyone with
that key can already decrypt whatever was written with it. The goal is to
stop using the compromised key going forward and shrink the exposure window,
not to undo past exposure.

1. Generate a new key and **prepend** it to `MESSAGE_ENCRYPTION_KEYS` in the
   env (`.env` / deployment secret), keeping the old key after it:
   ```
   MESSAGE_ENCRYPTION_KEYS=<new_key>,<old_key>
   ```
   New messages are now encrypted with `<new_key>`; old messages still
   decrypt because `<old_key>` is still listed.
2. Deploy / restart so the new setting takes effect.
3. Run the migration command to re-encrypt every existing row onto the new
   active key:
   ```
   python manage.py reencrypt_messages
   ```
   See `apps/messaging/management/commands/reencrypt_messages.py` for
   `--batch-size`, `--start-id` (resume after an interrupted run), and
   `--sleep` (throttle between batches on a live DB).
4. Once the command finishes ("Done. Re-encrypted N messages."), remove
   `<old_key>` from `MESSAGE_ENCRYPTION_KEYS` entirely:
   ```
   MESSAGE_ENCRYPTION_KEYS=<new_key>
   ```
   Keeping a compromised key around longer than the migration takes only
   adds risk for no benefit - it's a temporary bridge, not a backup.

## Mixed key-history scenarios

`reencrypt_messages` is not required after every rotation for reads to keep
working - it's a hygiene step, not a correctness requirement. As long as
**every key that was ever active is still listed** in
`MESSAGE_ENCRYPTION_KEYS`, rows written under any of them (or before
encryption existed at all) remain readable indefinitely, in any mix.

### Rotating multiple times without ever running the command

Say the key history is: no key -> key A -> key B -> key C, and
`reencrypt_messages` was never run. The messages table now holds four kinds
of row at once: plaintext (from before any key existed), ciphertext-under-A,
ciphertext-under-B, ciphertext-under-C. This is fine, provided the current
config lists all of them:

```
MESSAGE_ENCRYPTION_KEYS=C,B,A
```

`MultiFernet` tries C, then B, then A on every read, so each row decrypts
under whichever key it was actually written with; a plaintext row fails all
three and falls through to the passthrough path, returning the original
text unchanged. Nothing breaks - the only cost is that A and B must stay in
the env forever (or until migrated), which grows the list with every
rotation and keeps more historical keys "live" than necessary.

### Running the command once, after several rotations

You don't need to migrate stage by stage (A->B, then B->C). One run of
`reencrypt_messages`, with the full key history still configured
(`MESSAGE_ENCRYPTION_KEYS=C,B,A`, C active), converges every row straight to
C in a single pass - each row is decrypted with whichever key matches it
(A, B, C, or none) and re-encrypted with the active key (C) on save. After
it finishes, `A` and `B` can both be dropped at once:

```
MESSAGE_ENCRYPTION_KEYS=C
```

### The failure mode to avoid

If a key is removed from `MESSAGE_ENCRYPTION_KEYS` **before**
`reencrypt_messages` has migrated the rows encrypted under it, those rows
become permanently unreadable - decryption fails under every remaining key,
the passthrough path returns raw ciphertext instead of the original text,
and there is no way to recover it without the dropped key. This cannot
happen to plaintext rows (they never depended on any key), only to rows
that were actually encrypted under the key being removed. The rule is
always: **keep every key that's ever been used until `reencrypt_messages`
has run with all of them configured, then drop the retired ones.**

## Scale note

`reencrypt_messages` walks messages in `id`-ordered batches
(`Message.objects.filter(id__gt=last_id).order_by("id")[:batch_size]`)
rather than loading the whole table, and uses per-row `.save()` (so both
decrypt-on-read and encrypt-on-write go through the normal field logic). It
is safe to re-run: re-encrypting an already-migrated row with the same
active key is a no-op change. For very large tables, run it during low
traffic and/or pass `--sleep` to avoid saturating the DB.
