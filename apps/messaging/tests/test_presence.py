from django.test import SimpleTestCase

from apps.messaging.presence import InMemoryPresenceBackend


class InMemoryPresenceBackendTests(SimpleTestCase):
    def test_goes_offline_only_after_the_last_connection_closes(self):
        backend = InMemoryPresenceBackend()
        self.assertFalse(backend.is_online(1))

        self.assertEqual(backend.connect(1), 1)  # tab 1
        self.assertTrue(backend.is_online(1))

        self.assertEqual(backend.connect(1), 2)  # tab 2, same user
        self.assertEqual(backend.disconnect(1), 1)  # tab 1 closes
        self.assertTrue(backend.is_online(1))  # still online via tab 2

        self.assertEqual(backend.disconnect(1), 0)  # tab 2 closes
        self.assertFalse(backend.is_online(1))

    def test_disconnect_without_a_matching_connect_does_not_go_negative(self):
        backend = InMemoryPresenceBackend()
        self.assertEqual(backend.disconnect(1), 0)
        self.assertFalse(backend.is_online(1))

    def test_online_user_ids_filters_to_currently_connected(self):
        backend = InMemoryPresenceBackend()
        backend.connect(1)
        backend.connect(2)
        backend.disconnect(2)
        self.assertEqual(backend.online_user_ids([1, 2, 3]), {1})
