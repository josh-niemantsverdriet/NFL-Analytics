"""Descriptive season comparisons; these are not trained game predictions."""

from math import isfinite


METRICS = (
    ("epa_per_play", "def_epa_per_play", "expected_epa_per_play"),
    ("pass_epa_per_play", "def_pass_epa_per_play", "expected_pass_epa_per_play"),
    ("rush_epa_per_play", "def_rush_epa_per_play", "expected_rush_epa_per_play"),
    ("success_rate", "def_success_rate_allowed", "expected_success_rate"),
    ("explosive_play_rate", "def_explosive_play_rate_allowed", "expected_explosive_rate"),
)


def blend_matchup_metrics(offense, defense):
    result = {"team": offense["team"], "opponent": defense["team"]}
    for attack_key, defense_key, output_key in METRICS:
        values = (offense.get(attack_key), defense.get(defense_key))
        result[output_key] = (
            sum(values) / 2 if all(value is not None and isfinite(value) for value in values) else None
        )
    return result
