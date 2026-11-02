import unittest
from reliable_agents import ApprovalRequired, Handoff, IdempotencyConflict, PolicyError, TrustedIdentity
from reliable_agents.demo import RoomService, build_gateway


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.service = RoomService()
        self.gateway = build_gateway(self.service)
        self.identity = TrustedIdentity("test-user", "tenant-a")

    def test_search_filters_capacity(self):
        result = self.gateway.execute("find_rooms", {"min_seats": 7}, self.identity)
        self.assertEqual(result["rooms"], [{"id": "cedar", "seats": 10}])

    def test_unknown_tool_is_blocked(self):
        with self.assertRaises(PolicyError):
            self.gateway.execute("dangerous_shell", {}, self.identity)

    def test_side_effect_requires_approval(self):
        with self.assertRaises(ApprovalRequired):
            self.gateway.execute("reserve_room", {"room_id": "atlas", "date": "2026-12-01"}, self.identity, idempotency_key="k1")

    def test_side_effect_requires_key(self):
        with self.assertRaises(PolicyError):
            self.gateway.execute("reserve_room", {"room_id": "atlas", "date": "2026-12-01"}, self.identity, approved=True)

    def test_replay_does_not_duplicate_write(self):
        args = {"room_id": "atlas", "date": "2026-12-01"}
        first = self.gateway.execute("reserve_room", args, self.identity, approved=True, idempotency_key="abc")
        second = self.gateway.execute("reserve_room", args, self.identity, approved=True, idempotency_key="abc")
        self.assertEqual(first, second)
        self.assertEqual(len(self.service.reservations), 1)

    def test_replay_conflict_is_rejected(self):
        self.gateway.execute("reserve_room", {"room_id": "atlas", "date": "2026-12-01"}, self.identity, approved=True, idempotency_key="k1")
        with self.assertRaises(IdempotencyConflict):
            self.gateway.execute("reserve_room", {"room_id": "maple", "date": "2026-12-01"}, self.identity, approved=True, idempotency_key="k1")

    def test_tenant_scoping(self):
        a = self.gateway.execute("reserve_room", {"room_id": "atlas", "date": "2026-12-01"}, self.identity, approved=True, idempotency_key="same")
        b = self.gateway.execute("reserve_room", {"room_id": "atlas", "date": "2026-12-01"}, TrustedIdentity("test-user", "tenant-b"), approved=True, idempotency_key="same")
        self.assertEqual(a, b)
        self.assertEqual(len(self.service.reservations), 2)

    def test_no_credentials_in_handoff(self):
        with self.assertRaises(ValueError):
            Handoff("task", "booking", "reserve", "atlas", {"api_key": "not-for-handoff"})

    def test_approved_does_not_override_validation(self):
        with self.assertRaises(ValueError):
            self.gateway.execute("reserve_room", {"room_id": "unknown", "date": "2026-12-01"}, self.identity, approved=True, idempotency_key="k1")

    def test_nested_credentials_in_handoff_are_rejected(self):
        with self.assertRaises(ValueError):
            Handoff("task", "booking", "reserve", "atlas", {"nested": {"access_token": "not-for-handoff"}})

    def test_invalid_date_rejected(self):
        with self.assertRaises(ValueError):
            self.gateway.execute("reserve_room", {"room_id": "atlas", "date": "2026-02-31"}, self.identity, approved=True, idempotency_key="bad-date")

    def test_non_json_input_rejected(self):
        with self.assertRaises(PolicyError):
            self.gateway.execute("find_rooms", {"min_seats": object()}, self.identity)


if __name__ == "__main__":
    unittest.main()
