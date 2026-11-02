"""Fully local reservation simulation. No external services or real bookings."""
import json
from datetime import date as calendar_date
from typing import Any
from .contracts import Handoff, TrustedIdentity
from .gateway import ToolGateway, ToolSpec


class RoomService:
    def __init__(self) -> None:
        self.rooms = {"atlas": 6, "cedar": 10, "maple": 4}
        self.reservations: dict[tuple[str, str, str], str] = {}

    def find(self, args: dict[str, Any], identity: TrustedIdentity) -> dict[str, Any]:
        min_seats = args.get("min_seats")
        if type(min_seats) is not int or not 1 <= min_seats <= 50:
            raise ValueError("min_seats must be an integer between 1 and 50")
        return {"rooms": [{"id": room, "seats": seats} for room, seats in sorted(self.rooms.items()) if seats >= min_seats]}

    def reserve(self, args: dict[str, Any], identity: TrustedIdentity) -> dict[str, Any]:
        room_id, date = args.get("room_id"), args.get("date")
        if not isinstance(room_id, str) or room_id not in self.rooms:
            raise ValueError("Unknown room_id")
        if not isinstance(date, str):
            raise ValueError("date must be YYYY-MM-DD")
        try:
            parsed = calendar_date.fromisoformat(date)
        except ValueError as exc:
            raise ValueError("date must be a valid YYYY-MM-DD date") from exc
        if parsed.isoformat() != date:
            raise ValueError("date must be YYYY-MM-DD")
        # This demo allows one reservation per tenant/room/date.
        key = (identity.tenant_id, room_id, date)
        if key in self.reservations:
            raise ValueError("Room is already reserved for this tenant and date")
        self.reservations[key] = identity.actor_id
        return {"status": "reserved-in-demo", "room_id": room_id, "date": date}


def build_gateway(service: RoomService) -> ToolGateway:
    return ToolGateway([
        ToolSpec(name="find_rooms", handler=service.find),
        ToolSpec(name="reserve_room", handler=service.reserve, side_effect=True),
    ])


def main() -> None:
    identity = TrustedIdentity(actor_id="demo-user", tenant_id="demo-tenant")
    service = RoomService()
    gateway = build_gateway(service)
    rooms = gateway.execute("find_rooms", {"min_seats": 6}, identity)
    handoff = Handoff(task_id="task-001", target="reservation", intent="reserve_room", selected_id=rooms["rooms"][0]["id"], metadata={"date": "2026-12-01"})
    # Approval is deliberately granted by application code, not by model output.
    result = gateway.execute("reserve_room", {"room_id": handoff.selected_id, "date": handoff.metadata["date"]}, identity, approved=True, idempotency_key=handoff.task_id)
    replay = gateway.execute("reserve_room", {"room_id": handoff.selected_id, "date": handoff.metadata["date"]}, identity, approved=True, idempotency_key=handoff.task_id)
    print(json.dumps({"available": rooms, "handoff_target": handoff.target, "result": result, "replay": replay}, indent=2))


if __name__ == "__main__":
    main()
