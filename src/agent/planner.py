from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PlanStep:
    name: str
    status: str = "pending"


def build_plan() -> list[PlanStep]:
    return [
        PlanStep(name="Understand"),
        PlanStep(name="CheckMissingInfo"),
        PlanStep(name="GatherData"),
        PlanStep(name="RankOptions"),
        PlanStep(name="Explain"),
    ]
