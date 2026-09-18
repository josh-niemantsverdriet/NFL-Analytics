"""Team efficiency on regular-season offensive plays, using nflfastR definitions."""

import polars as pl


def calculate_team_analytics(play_by_play: pl.DataFrame, season: int, snapshot_date: str) -> pl.DataFrame:
    columns = set(play_by_play.columns)

    def flag(name):
        return pl.col(name).fill_null(0) == 1 if name in columns else pl.lit(False)

    # nflfastR pass/rush classify sacks and scrambles as dropbacks. Fall back
    # to component flags for older snapshots without these derived columns.
    passing = flag("pass") if "pass" in columns else (
        flag("qb_dropback") | flag("pass_attempt") | flag("sack") | flag("qb_scramble")
    )
    rushing = (flag("rush") if "rush" in columns else flag("rush_attempt")) & ~passing
    valid = (
        pl.col("posteam").is_not_null() & (pl.col("posteam") != "")
        & pl.col("defteam").is_not_null() & (pl.col("defteam") != "")
        & (pl.col("posteam") != pl.col("defteam"))
        & pl.col("epa").is_finite()
        & (passing | rushing)
        & ~flag("qb_kneel") & ~flag("qb_spike")
    )
    if "season" in columns:
        valid &= pl.col("season") == season
    if "season_type" in columns:
        valid &= pl.col("season_type") == "REG"
    plays = play_by_play.filter(valid).with_columns(passing.alias("_pass"), rushing.alias("_rush"))

    def aggregate(team_column, defensive=False):
        names = (
            ["def_plays", "def_epa_per_play", "def_pass_epa_per_play", "def_rush_epa_per_play",
             "def_success_rate_allowed", "def_explosive_play_rate_allowed"]
            if defensive else
            ["plays", "epa_per_play", "pass_epa_per_play", "rush_epa_per_play", "success_rate", "explosive_play_rate"]
        )
        expressions = [
            pl.len(), pl.col("epa").mean(),
            pl.col("epa").filter(pl.col("_pass")).mean(),
            pl.col("epa").filter(pl.col("_rush")).mean(),
            (pl.col("epa") > 0).mean(),
            (pl.col("yards_gained") >= 20).mean(),
        ]
        metrics = [expression.alias(name) for expression, name in zip(expressions, names)]
        if not defensive:
            metrics.append(pl.col("_pass").mean().alias("pass_rate"))
        return plays.group_by(team_column).agg(metrics).rename({team_column: "team"})

    return (
        aggregate("posteam").join(aggregate("defteam", True), on="team", how="full", coalesce=True)
        .with_columns(
            pl.lit(season).alias("season"),
            pl.lit(snapshot_date).str.to_date("%Y-%m-%d").alias("snapshot_date"),
            pl.col("plays").fill_null(0), pl.col("def_plays").fill_null(0),
        )
        .select(
            "season", "snapshot_date", "team", "plays", "epa_per_play", "pass_epa_per_play",
            "rush_epa_per_play", "success_rate", "explosive_play_rate", "pass_rate",
            "def_plays", "def_epa_per_play", "def_pass_epa_per_play", "def_rush_epa_per_play",
            "def_success_rate_allowed", "def_explosive_play_rate_allowed",
        )
        .sort("epa_per_play", descending=True, nulls_last=True)
    )
