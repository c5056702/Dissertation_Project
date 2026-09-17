"""Current route wording shared by the console and live dashboard."""

from typing import Any


MOVING_STATES = {"NAVIGATING", "TO_PICKUP", "TO_DROPOFF", "TO_RETURN"}
ARRIVAL_STATES = {"ARRIVED", "AT_PICKUP", "AT_DROPOFF"}


def pending_route_destination(snapshot: dict[str, Any]) -> str | None:
    command = str(snapshot.get("pending_command") or "")
    if command.startswith(("go to ", "start ")):
        return command[-1].upper()
    return snapshot.get("pending_destination") if command else None


def route_status_text(snapshot: dict[str, Any]) -> str:
    """Describe the current selection, never a cached tilt instruction."""
    state = str(snapshot.get("state") or "IDLE")
    if state in {"IDLE", "STOPPED"}:
        return "None - START required"
    if snapshot.get("route_selection_error"):
        return str(snapshot["route_selection_error"])
    destination = pending_route_destination(snapshot)
    if destination:
        command = str(snapshot.get("pending_command") or "")
        if not command.startswith(("go to ", "start ")):
            return f"{destination}: task confirmation pending"
        choice = snapshot.get("pending_route_choice") or snapshot.get("route_choice")
        if choice in {"alternative", "long"}:
            return f"TO {destination}: ALTERNATIVE - awaiting NOD"
        if choice in {"shortest", "short"} or command.startswith("go to "):
            return f"TO {destination}: SHORTEST - awaiting NOD"
        return f"TO {destination}: choose LEFT or RIGHT"
    if state in ARRIVAL_STATES:
        return f"AT {snapshot.get('current_location') or snapshot.get('destination') or '?'} - arrived"
    if snapshot.get("active_destination") and state in MOVING_STATES | {"PAUSED"}:
        choice = str(snapshot.get("active_route_choice") or "route confirmed").upper()
        phase = "navigating" if state in MOVING_STATES else "paused"
        return f"TO {snapshot['active_destination']}: {choice} - {phase}"
    return "None - choose a destination"
