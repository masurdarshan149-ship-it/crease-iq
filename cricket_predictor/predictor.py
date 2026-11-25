from __future__ import annotations

from dataclasses import dataclass, field

from .models import MatchContext, Player, TeamSnapshot


@dataclass(slots=True)
class PredictionResult:
    batting_first_team: str
    chasing_team: str
    batting_first_win_probability: float
    chasing_win_probability: float
    predicted_winner: str
    confidence: float
    explanation: list[str]
    model_used: str = "formula"
    details: dict = field(default_factory=dict)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _mean(values: list[float], default: float) -> float:
    return sum(values) / len(values) if values else default


def _player_batting_impact(player: Player) -> float:
    return (
        player.batting_average * 0.35
        + player.strike_rate * 0.18
        + player.recent_form * 35.0
        + player.fitness * 12.0
    )


def _player_bowling_impact(player: Player) -> float:
    bowling_average = player.bowling_average if player.bowling_average > 0 else 45.0
    economy_rate = player.economy_rate if player.economy_rate > 0 else 9.0
    return (
        (50.0 - bowling_average) * 1.1
        + (10.0 - economy_rate) * 7.5
        + player.recent_form * 32.0
        + player.fitness * 10.0
    )


def _team_batting_strength(team: TeamSnapshot) -> float:
    player_scores = [
        _player_batting_impact(player)
        for player in team.players
        if player.role in {"batter", "all_rounder", "wicket_keeper"}
    ]
    return team.batting_rating * 0.55 + _mean(player_scores, 55.0) * 0.45 + team.recent_form * 22.0


def _team_bowling_strength(team: TeamSnapshot) -> float:
    player_scores = [
        _player_bowling_impact(player)
        for player in team.players
        if player.role in {"bowler", "all_rounder"}
    ]
    return team.bowling_rating * 0.55 + _mean(player_scores, 45.0) * 0.45 + team.recent_form * 18.0


def _innings_phase_factor(context: MatchContext) -> float:
    max_overs = {"t20": 20.0, "odi": 50.0, "test": 90.0}.get(context.format, 20.0)
    completion = _clamp(context.overs_faced / max_overs, 0.0, 1.0)
    wickets_pressure = context.wickets_lost / 10.0
    return completion * 0.7 + (1.0 - wickets_pressure) * 0.3


def predict_with_formula(context: MatchContext) -> PredictionResult:
    """Original hand-weighted formula. Kept as a fallback and for comparison."""
    batting_team = context.batting_first_team
    chasing_team = context.chasing_team
    pitch = context.pitch_report

    batting_strength = _team_batting_strength(batting_team)
    defending_strength = _team_bowling_strength(batting_team)
    chase_batting_strength = _team_batting_strength(chasing_team)
    chasing_bowling_strength = _team_bowling_strength(chasing_team)

    score_delta = context.first_innings_score - pitch.average_first_innings_score
    phase_factor = _innings_phase_factor(context)

    # ODI/Test scoring is less volatile — a run-lead carries less absolute weight
    format_score_scale = {"t20": 1.0, "odi": 0.65, "test": 0.38}.get(context.format, 1.0)
    score_component = score_delta * 0.55 * format_score_scale

    # Format-aware wicket baseline: typical end-of-innings wickets lost
    wicket_baseline = {"t20": 5, "odi": 6, "test": 10}.get(context.format, 5)
    wicket_scale = {"t20": 3.2, "odi": 2.0, "test": 0.6}.get(context.format, 3.2)
    wicket_component = (wicket_baseline - context.wickets_lost) * wicket_scale

    overs_component = (phase_factor - 0.5) * 18.0

    batting_advantage = batting_strength - chasing_bowling_strength
    bowling_advantage = defending_strength - chase_batting_strength
    net_strength_delta = batting_advantage * 0.18 + bowling_advantage * 0.22

    pitch_bowling_diff = defending_strength - chase_batting_strength
    pitch_component = (
        pitch.pace_assist * pitch_bowling_diff * 0.08
        + pitch.spin_assist * pitch_bowling_diff * 0.06
        + pitch.batting_friendliness * -6.0
    )

    # Dew is irrelevant in multi-day test cricket
    dew_component = 0.0 if context.format == "test" else (-7.0 if pitch.dew_expected else 0.0)

    fielding_component = (batting_team.fielding_rating - chasing_team.fielding_rating) * 0.25
    form_component = (batting_team.recent_form - chasing_team.recent_form) * 18.0

    raw_score = (
        50.0
        + score_component
        + wicket_component
        + overs_component
        + net_strength_delta
        + pitch_component
        + dew_component
        + fielding_component
        + form_component
    )

    batting_first_win_probability = _clamp(raw_score, 5.0, 95.0)
    chasing_win_probability = 100.0 - batting_first_win_probability
    predicted_winner = (
        batting_team.name
        if batting_first_win_probability >= chasing_win_probability
        else chasing_team.name
    )

    confidence = abs(batting_first_win_probability - chasing_win_probability)

    format_label = {"t20": "T20", "odi": "ODI", "test": "Test"}.get(context.format, context.format.upper())
    fielding_edge = batting_team.fielding_rating - chasing_team.fielding_rating
    dew_note = " | Dew expected — advantage to chasing side." if pitch.dew_expected and context.format != "test" else ""
    explanation = [
        f"{batting_team.name} scored {context.first_innings_score} ({format_label}), {score_delta:+.0f} vs pitch average of {pitch.average_first_innings_score:.0f}.",
        f"Batting-first strength — bat: {batting_strength:.1f}, bowl: {defending_strength:.1f} vs chasing bat: {chase_batting_strength:.1f}, bowl: {chasing_bowling_strength:.1f}.",
        f"Pitch: batting={pitch.batting_friendliness:+.2f}, pace={pitch.pace_assist:+.2f}, spin={pitch.spin_assist:+.2f}{dew_note}",
        f"Fielding edge: {batting_team.name} ({batting_team.fielding_rating:.0f}) vs {chasing_team.name} ({chasing_team.fielding_rating:.0f}) — net {fielding_edge:+.1f}.",
        f"Recent form: {batting_team.name} {batting_team.recent_form:.0%} vs {chasing_team.name} {chasing_team.recent_form:.0%}.",
    ]

    return PredictionResult(
        batting_first_team=batting_team.name,
        chasing_team=chasing_team.name,
        batting_first_win_probability=round(batting_first_win_probability, 2),
        chasing_win_probability=round(chasing_win_probability, 2),
        predicted_winner=predicted_winner,
        confidence=round(confidence, 2),
        explanation=explanation,
    )


def predict_match_winner(context: MatchContext) -> PredictionResult:
    """Use the trained ML model when available; otherwise the original formula."""
    formula = predict_with_formula(context)
    try:
        from . import ml_model

        result = ml_model.predict(context, formula_probability=formula.batting_first_win_probability)
    except Exception as exc:  # never let a model problem break the app
        formula.explanation.append(f"ML model unavailable ({type(exc).__name__}); using the original formula.")
        return formula
    if result is None:
        if context.format not in {"t20", "odi"}:
            formula.explanation.append("The ML model covers T20 and ODI only; Test matches use the original formula.")
        return formula
    return result
