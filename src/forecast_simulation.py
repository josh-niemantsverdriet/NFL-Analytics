"""Seeded synthetic NFL-like seasons and an offline model stress runner.

Simulation validates invariants under controlled changes; it is not evidence
of accuracy on real NFL games. Scores arise from touchdowns, field goals and
safeties, with shared game pace and evolving team strengths.
"""

import argparse
from datetime import date, timedelta
import json
from time import perf_counter

import numpy as np


TEAMS = (
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
    "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
    "LA", "LAC", "LV", "MIA", "MIN", "NE", "NO", "NYG",
    "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
)
SCENARIOS = ("balanced", "unequal", "drifting", "volatile", "low_scoring", "high_scoring")


def simulate_seasons(seed=0, seasons=4, scenario="balanced"):
    if seasons < 1 or seasons > 30 or scenario not in SCENARIOS:
        raise ValueError("Choose 1–30 seasons and a supported scenario.")
    rng = np.random.default_rng(seed)
    strength_scale = 0.32 if scenario == "unequal" else 0.14
    offense = rng.normal(0, strength_scale, 32)
    defense = rng.normal(0, strength_scale, 32)
    home_effects = rng.normal(0.05, 0.025, 32)
    base_points = {"low_scoring": 10.0, "high_scoring": 37.0}.get(scenario, 22.0)
    pace_scale = 0.32 if scenario == "volatile" else 0.12
    games = []

    def play(home, away, day, season, week, postseason=False):
        neutral = postseason or bool(rng.random() < 0.06)
        pace = rng.lognormal(-pace_scale ** 2 / 2, pace_scale)
        means = base_points * np.exp(np.clip(np.array([
            offense[home] + defense[away] + (0 if neutral else home_effects[home]),
            offense[away] + defense[home] - (0 if neutral else home_effects[home]),
        ]), -1.1, 1.1)) * pace
        # 75% of expected points from touchdowns, 24% field goals, 1% safeties.
        touchdowns = rng.poisson(means * 0.75 / 7)
        scores = 6 * touchdowns + rng.binomial(touchdowns, 0.96)
        scores += 3 * rng.poisson(means * 0.24 / 3) + 2 * rng.poisson(means * 0.01 / 2)
        # Stylized overtime resolves most regular-season ties and all playoffs.
        if scores[0] == scores[1] and (postseason or rng.random() < 0.94):
            winner = int(rng.random() >= means[0] / means.sum())
            scores[winner] += int(rng.choice([3, 6]))
        games.append({
            "game_id": f"sim-{seed}-{season}-{week}-{TEAMS[home]}-{TEAMS[away]}",
            "season": season, "week": week, "gameday": day.isoformat(),
            "gametime": "13:00", "game_type": "SB" if postseason else "REG",
            "home_team": TEAMS[home], "away_team": TEAMS[away],
            "home_score": int(scores[0]), "away_score": int(scores[1]),
            "location": "Neutral" if neutral else "Home",
        })

    for year in range(seasons):
        season = 2010 + year
        first_day = date(season, 9, 1)
        first_day += timedelta(days=(6 - first_day.weekday()) % 7)
        order = list(rng.permutation(32))
        for week in range(17):
            if scenario == "drifting":
                offense = np.clip(offense + rng.normal(0, 0.025, 32), -0.5, 0.5)
                defense = np.clip(defense + rng.normal(0, 0.025, 32), -0.5, 0.5)
            for pair in range(16):
                home, away = order[pair], order[-pair - 1]
                # Rotating positions already alternate parity. Adding week
                # parity here would accidentally keep some teams always away.
                if (pair == 0 and week % 2) or (pair != 0 and pair % 2):
                    home, away = away, home
                play(home, away, first_day + timedelta(weeks=week), season, week + 1)
            order = [order[0], order[-1], *order[1:-1]]
        finalists = rng.choice(32, size=2, replace=False)
        play(*finalists, first_day + timedelta(weeks=22), season, 23, postseason=True)
        offense = 0.8 * offense + rng.normal(0, 0.06, 32)
        defense = 0.8 * defense + rng.normal(0, 0.06, 32)
    return games


def run_stress(seeds=32, seasons=6, matchups=64):
    from src.forecast_model import _clean_games, _fit, _forecast

    started = perf_counter()
    game_count = forecast_count = 0
    scenario_counts = {name: 0 for name in SCENARIOS}
    failures = []
    for seed in range(seeds):
        scenario = SCENARIOS[seed % len(SCENARIOS)]
        raw = simulate_seasons(seed, seasons, scenario)
        game_count += len(raw)
        scenario_counts[scenario] += 1
        cleaned, discarded, duplicates = _clean_games(raw)
        if discarded or duplicates:
            failures.append({"seed": seed, "error": "Valid simulated history was discarded."})
            continue
        model = _fit(cleaned)
        rng = np.random.default_rng(seed + 10000)
        for index in range(matchups):
            home, away = rng.choice(TEAMS, 2, replace=False)
            try:
                forecast = _forecast(model, home, away, neutral=index % 3 == 0, allow_ties=index % 4 != 0)
                json.dumps(forecast, allow_nan=False)
                chances = [forecast[key] for key in ("home_win_probability", "away_win_probability", "tie_probability")]
                if min(chances) < 0 or abs(sum(chances) - 1) > 1e-8:
                    raise AssertionError("Outcome probabilities do not form a distribution.")
                if not forecast["allow_ties"] and forecast["tie_probability"] != 0:
                    raise AssertionError("Postseason tie probability must be zero.")
                forecast_count += 1
            except (ValueError, AssertionError) as error:
                failures.append({"seed": seed, "scenario": scenario, "matchup": [str(home), str(away)], "error": str(error)})
    return {
        "synthetic": True, "seeds": seeds, "seasons_per_seed": seasons,
        "simulated_games": game_count, "forecasts_checked": forecast_count,
        "scenarios": scenario_counts, "failures": failures,
        "seconds": round(perf_counter() - started, 3),
        "interpretation": "Robustness checks on simulated data, not measured real-game accuracy.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=32)
    parser.add_argument("--seasons", type=int, default=6)
    parser.add_argument("--matchups", type=int, default=64)
    args = parser.parse_args()
    if args.seeds < 1 or args.matchups < 1:
        parser.error("Seeds and matchups must be positive.")
    report = run_stress(args.seeds, args.seasons, args.matchups)
    print(json.dumps(report, indent=2, allow_nan=False))
    if report["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
