"""JSON-lines runtime evidence logging for each isolated validation run."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4


class ValidationLogger:
    def __init__(self, run_dir: Path, *, append: bool = False) -> None:
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.run_dir / "controller_events.ndjson"
        if not append or not self.events_path.exists():
            self.events_path.write_text("", encoding="utf-8")
        self.events: list[dict[str, Any]] = []
        self.session_id = uuid4().hex[:12]
        self.listeners: list[Callable[[dict[str, Any]], None]] = []

    def add_listener(self, listener: Callable[[dict[str, Any]], None]) -> None:
        self.listeners.append(listener)

    def event(self, name: str, **details: Any) -> dict[str, Any]:
        entry = {"event": name, "time": round(time.time(), 3), "session_id": self.session_id, **details}
        self.events.append(entry)
        with self.events_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, sort_keys=True) + "\n")
        for listener in tuple(self.listeners):
            try:
                listener(entry)
            except Exception:
                # Trace displays must never interfere with robot safety logic.
                pass
        return entry

    def result(self, **details: Any) -> None:
        commands = [event for event in self.events if event["event"] == "command_recognised"]
        gestures = [event for event in self.events if event["event"] == "gesture_recognised"]
        accepted_commands = [event for event in commands if event.get("accepted")]
        pending_commands = [event for event in accepted_commands if event.get("status") == "pending_confirmation"]
        rejected_commands = [event for event in commands if not event.get("accepted")]
        metrics = {
            "command_events": len(commands),
            "accepted_command_events": len(accepted_commands),
            "rejected_command_events": len(rejected_commands),
            "command_acceptance_rate": round(len(accepted_commands) / len(commands), 4) if commands else None,
            "gesture_events": len(gestures),
            "recognised_gesture_events": sum(event.get("outcome") not in {"ignored_gesture", "gesture_ignored"} for event in gestures),
            "route_starts": sum(event["event"] == "route_started" for event in self.events),
            "navigation_pauses": sum(event["event"] == "navigation_paused" for event in self.events),
            "navigation_resumes": sum(event["event"] == "navigation_resumed" for event in self.events),
            "destination_changes": sum(bool(event.get("in_motion")) and str(event.get("command", "")).startswith("go to ") for event in commands),
            "waypoint_events": sum(event["event"] == "waypoint_reached" for event in self.events),
            "safety_stops": sum(event["event"] == "safety_stop" for event in self.events),
            "route_failures": sum(event["event"] == "route_failed" for event in self.events),
        }
        recognised_times = [event["time"] for event in pending_commands]
        confirmed_times = [event["time"] for event in self.events if event["event"] == "command_confirmed"]
        response_times = [round(confirmed - recognised, 3) for recognised, confirmed in zip(recognised_times, confirmed_times)]
        if response_times:
            metrics["confirmation_response_seconds"] = response_times
            metrics["mean_confirmation_response_seconds"] = round(sum(response_times) / len(response_times), 3)
        if self.events:
            metrics["wall_clock_duration_seconds"] = round(time.time() - self.events[0]["time"], 3)
        if "pass_result" in details:
            metrics["successful_execution"] = bool(details["pass_result"])
        payload = {"events": self.events, "metrics": metrics, **details}
        (self.run_dir / "result.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
