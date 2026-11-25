from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


MatchFormat = Literal["t20", "odi", "test"]
PlayerRole = Literal["batter", "bowler", "all_rounder", "wicket_keeper"]


@dataclass(slots=True)
class Player:
    name: str
    role: PlayerRole
    batting_average: float = 0.0
    strike_rate: float = 0.0
    bowling_average: float = 0.0
    economy_rate: float = 0.0
    recent_form: float = 0.5
    fitness: float = 1.0


@dataclass(slots=True)
class TeamSnapshot:
    name: str
    players: list[Player] = field(default_factory=list)
    batting_rating: float = 50.0
    bowling_rating: float = 50.0
    fielding_rating: float = 50.0
    recent_form: float = 0.5


@dataclass(slots=True)
class PitchReport:
    average_first_innings_score: float
    batting_friendliness: float = 0.0
    pace_assist: float = 0.0
    spin_assist: float = 0.0
    dew_expected: bool = False


@dataclass(slots=True)
class MatchContext:
    format: MatchFormat
    batting_first_team: TeamSnapshot
    chasing_team: TeamSnapshot
    first_innings_score: int
    wickets_lost: int
    overs_faced: float
    pitch_report: PitchReport
    crease: dict | None = None  # {"bat": [{"name", "balls"}], "chase": [...]}: batters at the crease, if the user said
    venue: dict | None = None  # {"key", "kind", "name", "city"} of the chosen ground, when known (home advantage, venue bias)
    order: dict | None = None  # {"bat": [names] or None, "chase": ...}: the batting order the user dragged, if they did
