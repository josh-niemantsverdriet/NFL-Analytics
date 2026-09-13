import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import "./TeamPage.css";


interface Analytics {
  plays: number;
  epa_per_play: number | null;
  pass_epa_per_play: number | null;
  rush_epa_per_play: number | null;
  success_rate: number | null;
  explosive_play_rate: number | null;
  pass_rate: number | null;

  def_plays: number | null;
  def_epa_per_play: number | null;
  def_pass_epa_per_play: number | null;
  def_rush_epa_per_play: number | null;
  def_success_rate_allowed: number | null;
  def_explosive_play_rate_allowed: number | null;
}


interface Player {
  player_id: string;
  player_name: string;
  yards: number;
  touchdowns: number;
}


interface Game {
  week: number;
  date: string;
  away_team: string;
  away_score: number;
  home_team: string;
  home_score: number;
  result: string;
}


interface TeamData {
  team: string;
  season: number;
  snapshot_date: string;

  record: {
    wins: number;
    losses: number;
    ties: number;
  };

  rankings: {
    offense: number;
    defense: number;
    overall: number;
  };

  analytics: Analytics;

  leaders: {
    passing: Player[];
    rushing: Player[];
    receiving: Player[];
  };

  recent_games: Game[];
}


function formatEPA(
  value: number | null
) {
  if (value === null) {
    return "—";
  }

  return `${value >= 0 ? "+" : ""}${value.toFixed(3)}`;
}


function formatPercent(
  value: number | null
) {
  if (value === null) {
    return "—";
  }

  return `${(value * 100).toFixed(1)}%`;
}


function PlayerList({
  title,
  players,
}: {
  title: string;
  players: Player[];
}) {
  return (
    <div className="team-player-card">

      <div className="team-player-header">
        <h3>{title}</h3>
        <span>YDS</span>
      </div>

      {players.length === 0 ? (
        <p className="team-empty">
          No player data yet.
        </p>
      ) : (
        players.map(
          (player, index) => (
            <div
              className="team-player-row"
              key={player.player_id}
            >
              <span className="team-player-rank">
                {index + 1}
              </span>

              <div>
                <strong>
                  {player.player_name}
                </strong>

                <small>
                  {player.touchdowns} TD
                </small>
              </div>

              <strong>
                {player.yards}
              </strong>
            </div>
          )
        )
      )}

    </div>
  );
}


function TeamPage() {
  const { teamCode } = useParams();

  const [
    data,
    setData
  ] = useState<TeamData | null>(null);

  const [
    loading,
    setLoading
  ] = useState(true);

  const [
    error,
    setError
  ] = useState<string | null>(null);

  const apiBaseUrl =
    import.meta.env.VITE_API_BASE_URL;


  useEffect(() => {
    const loadTeam = async () => {
      if (!teamCode) {
        setError("Missing team code.");
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError(null);

        const response = await fetch(
          `${apiBaseUrl}/api/team/${encodeURIComponent(
            teamCode.toUpperCase()
          )}`
        );

        const body = await response.json();

        if (!response.ok) {
          throw new Error(
            body.error
            ?? `Team API returned ${response.status}`
          );
        }

        setData(body);

      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to load team."
        );
      } finally {
        setLoading(false);
      }
    };

    loadTeam();

  }, [
    teamCode,
    apiBaseUrl
  ]);


  if (loading) {
    return (
      <main className="page centered">
        <p>
          Loading team...
        </p>
      </main>
    );
  }


  if (error || !data) {
    return (
      <main className="page centered">

        <h1>
          Team not found
        </h1>

        <p className="error">
          {error}
        </p>

        <Link
          className="team-back-link"
          to="/"
        >
          Back to dashboard
        </Link>

      </main>
    );
  }


  const recordText =
    data.record.ties > 0
      ? `${data.record.wins}-${data.record.losses}-${data.record.ties}`
      : `${data.record.wins}-${data.record.losses}`;


  return (
    <main className="page">

      <Link
        to="/"
        className="team-back-link"
      >
        ← NFL Analytics
      </Link>


      <header className="team-page-header">

        <div>
          <p className="eyebrow">
            {data.season} TEAM PROFILE
          </p>

          <h1>
            {data.team}
          </h1>

          <p className="team-record">
            {recordText}
          </p>
        </div>


        <div className="team-ranking-summary">

          <div>
            <span>Overall</span>
            <strong>
              #{data.rankings.overall}
            </strong>
          </div>

          <div>
            <span>Offense</span>
            <strong>
              #{data.rankings.offense}
            </strong>
          </div>

          <div>
            <span>Defense</span>
            <strong>
              #{data.rankings.defense}
            </strong>
          </div>

        </div>

      </header>


      <section className="team-detail-section">

        <div className="section-title">

          <div>
            <p className="eyebrow">
              TEAM EFFICIENCY
            </p>

            <h2>
              Offense
            </h2>
          </div>

          <span>
            {data.analytics.plays} plays
          </span>

        </div>


        <div className="team-metric-grid">

          <div className="team-metric-card">
            <span>
              EPA / Play
            </span>

            <strong>
              {formatEPA(
                data.analytics.epa_per_play
              )}
            </strong>
          </div>


          <div className="team-metric-card">
            <span>
              Pass EPA
            </span>

            <strong>
              {formatEPA(
                data.analytics.pass_epa_per_play
              )}
            </strong>
          </div>


          <div className="team-metric-card">
            <span>
              Rush EPA
            </span>

            <strong>
              {formatEPA(
                data.analytics.rush_epa_per_play
              )}
            </strong>
          </div>


          <div className="team-metric-card">
            <span>
              Success Rate
            </span>

            <strong>
              {formatPercent(
                data.analytics.success_rate
              )}
            </strong>
          </div>


          <div className="team-metric-card">
            <span>
              Explosive Rate
            </span>

            <strong>
              {formatPercent(
                data.analytics.explosive_play_rate
              )}
            </strong>
          </div>


          <div className="team-metric-card">
            <span>
              Pass Rate
            </span>

            <strong>
              {formatPercent(
                data.analytics.pass_rate
              )}
            </strong>
          </div>

        </div>

      </section>


      <section className="team-detail-section">

        <div className="section-title">

          <div>
            <p className="eyebrow">
              OPPONENT EFFICIENCY
            </p>

            <h2>
              Defense
            </h2>
          </div>

          <span>
            {data.analytics.def_plays ?? "—"} plays
          </span>

        </div>


        <div className="team-metric-grid">

          <div className="team-metric-card">
            <span>
              EPA / Play Allowed
            </span>

            <strong>
              {formatEPA(
                data.analytics.def_epa_per_play
              )}
            </strong>
          </div>


          <div className="team-metric-card">
            <span>
              Pass EPA Allowed
            </span>

            <strong>
              {formatEPA(
                data.analytics.def_pass_epa_per_play
              )}
            </strong>
          </div>


          <div className="team-metric-card">
            <span>
              Rush EPA Allowed
            </span>

            <strong>
              {formatEPA(
                data.analytics.def_rush_epa_per_play
              )}
            </strong>
          </div>


          <div className="team-metric-card">
            <span>
              Success Allowed
            </span>

            <strong>
              {formatPercent(
                data.analytics.def_success_rate_allowed
              )}
            </strong>
          </div>


          <div className="team-metric-card">
            <span>
              Explosive Allowed
            </span>

            <strong>
              {formatPercent(
                data.analytics
                  .def_explosive_play_rate_allowed
              )}
            </strong>
          </div>

        </div>

      </section>


      <section className="team-detail-section">

        <div className="section-title">

          <div>
            <p className="eyebrow">
              TEAM LEADERS
            </p>

            <h2>
              Players
            </h2>
          </div>

        </div>


        <div className="team-player-grid">

          <PlayerList
            title="Passing"
            players={data.leaders.passing}
          />

          <PlayerList
            title="Rushing"
            players={data.leaders.rushing}
          />

          <PlayerList
            title="Receiving"
            players={data.leaders.receiving}
          />

        </div>

      </section>


      <section className="team-detail-section">

        <div className="section-title">

          <div>
            <p className="eyebrow">
              RESULTS
            </p>

            <h2>
              Recent Games
            </h2>
          </div>

        </div>


        <div className="team-games">

          {data.recent_games.length === 0 ? (
            <p className="team-empty">
              No completed games yet.
            </p>
          ) : (
            data.recent_games.map(
              (game) => (

                <div
                  className="team-game-row"
                  key={
                    `${game.week}-`
                    + `${game.away_team}-`
                    + `${game.home_team}`
                  }
                >

                  <span
                    className={
                      `team-result `
                      + `team-result-${game.result.toLowerCase()}`
                    }
                  >
                    {game.result}
                  </span>


                  <div className="team-game-week">
                    Week {game.week}
                    <small>
                      {game.date}
                    </small>
                  </div>


                  <div className="team-game-score">

                    <span>
                      {game.away_team}
                    </span>

                    <strong>
                      {game.away_score}
                    </strong>

                    <span>
                      {game.home_team}
                    </span>

                    <strong>
                      {game.home_score}
                    </strong>

                  </div>

                </div>
              )
            )
          )}

        </div>

      </section>


      <p className="team-data-date">
        Analytics snapshot: {data.snapshot_date}
      </p>

    </main>
  );
}


export default TeamPage;