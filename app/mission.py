"""Constrained deterministic schedule for an illustrative autonomous field test."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math

from pydantic import BaseModel, Field


class MissionRequest(BaseModel):
    survey_robots: int = Field(default=2, ge=0, le=8)
    excavators: int = Field(default=2, ge=0, le=8)
    builders: int = Field(default=3, ge=0, le=8)
    electricians: int = Field(default=1, ge=0, le=8)
    available_power_kw: float = Field(default=48, ge=5, le=500)


@dataclass(frozen=True, slots=True)
class Task:
    id: str
    label: str
    role: str
    base_hours: float
    power_kw: float
    dependencies: tuple[str, ...]


TASKS = (
    Task("survey", "Geotechnical survey", "survey_robots", 8, 4, ()),
    Task("prepare", "Excavate and prepare site", "excavators", 36, 14, ("survey",)),
    Task("foundation", "Fabricate foundation", "builders", 48, 13, ("prepare",)),
    Task("solar", "Install power system", "electricians", 31, 7, ("survey",)),
    Task("habitat", "Assemble habitat shell", "builders", 84, 19, ("foundation",)),
    Task("electrical", "Install electrical distribution", "electricians", 29, 8, ("habitat", "solar")),
    Task("inspection", "Inspect and commission", "survey_robots", 12, 5, ("electrical",)),
)


def simulate_mission(req: MissionRequest) -> dict:
    counts = req.model_dump()
    missing = sorted({task.role for task in TASKS if counts[task.role] == 0})
    if missing:
        return {"ready": False, "reason": "Required specialists missing", "missing_roles": missing, "timeline": []}
    done: dict[str, tuple[float, float]] = {}
    timeline: list[dict] = []
    for task in TASKS:
        efficiency = 1 + 0.55 * min(counts[task.role] - 1, 4)
        duration = round(task.base_hours / efficiency, 2)
        power = task.power_kw  # total task draw; avoid counting scaled robot count twice
        if power > req.available_power_kw:
            return {"ready": False, "reason": f"Insufficient available power for {task.label}", "required_power_kw": power, "timeline": []}
        start = max((done[dep][1] for dep in task.dependencies), default=0.0)
        # Earliest-feasible list schedule. Each task reserves its team type and power.
        for _ in range(len(TASKS) + 1):
            overlapping = [t for t in timeline if start < t["end_h"] and start + duration > t["start_h"]]
            conflict = any(t["role"] == task.role for t in overlapping)
            if not conflict:
                check_points = sorted({start, start + duration} | {max(start, t["start_h"]) for t in overlapping} | {min(start + duration, t["end_h"]) for t in overlapping})
                for a, b in zip(check_points, check_points[1:]):
                    if b <= a:
                        continue
                    midpoint = (a+b)*0.5
                    draw = power + sum(t["power_kw"] for t in overlapping if t["start_h"] <= midpoint < t["end_h"])
                    if draw > req.available_power_kw:
                        conflict = True
                        break
            if not conflict:
                break
            start = min(t["end_h"] for t in overlapping if t["end_h"] > start)
        else:
            raise RuntimeError("Could not allocate mission tasks deterministically")
        end = round(start + duration, 2)
        done[task.id] = (round(start, 2), end)
        timeline.append({"id": task.id, "label": task.label, "role": task.role, "start_h": round(start, 2), "end_h": end, "duration_h": duration, "power_kw": power, "energy_kwh": round(power * duration, 1)})
    total_h = max(item["end_h"] for item in timeline)
    return {
        "ready": True,
        "duration_h": total_h,
        "duration_days": round(total_h / 24, 1),
        "energy_kwh": round(sum(item["energy_kwh"] for item in timeline), 1),
        "timeline": timeline,
        "assumptions": [
            "Conceptual Earth analog demonstration, not a validated Mars deployment model.",
            "Task durations, robot productivity and electrical loads are illustrative.",
            "No material transport, launch costs, atmospheric, dust, communication, or weather constraints modeled.",
            "Schedule uses deterministic precedence, team exclusivity, and a shared power ceiling.",
        ],
    }
