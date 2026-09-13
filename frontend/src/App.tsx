import { useEffect, useState } from "react";
import { Link, Route, Routes } from "react-router";

import "./App.css";

import LeagueRankings from "./LeagueRankings";
import MatchupAnalyzer from "./MatchupAnalyzer";
import TeamPage from "./TeamPage";
import GameForecast from "./GameForecast";


interface Team {
  rank: number;
  team: string;
  plays: number;
  epa_per_play: number | null;
  success_rate: number | null;
  pass_epa_per_play: number | null;
  rush_epa_per_play: number | null;
}


interface PlayerLeader {
  rank: number;
  player_id: string;
  player_name: string;
  team: string;
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
}


interface DashboardData {
  season: number;
  snapshot_date: string;

  top_offenses: Team[];

  leaders: {
    passing: PlayerLeader[];
    rushing: PlayerLeader[];
    receiving: PlayerLeader[];
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


function LeaderList({
  title,
  players,
}: {
  title: string;
  players: PlayerLeader[];
}) {
  return (
    <section className="card leader-card">

      <div className="card-header">
        <h2>{title}</h2>
        <span>Yards</span>
      </div>


      <div className="leader-list">

        {players.length === 0 && (
          <p className="empty">
            No data available yet.
          </p>
        )}


        {players.map(
          (player) => (

            <div
              className="leader-row"
              key={player.player_id}
            >

              <div className="rank">
                {player.rank}
              </div>


              <div className="leader-name">

                <strong>
                  {player.player_name}
                </strong>

                <span>
                  {player.team} ·{" "}
                  {player.touchdowns} TD
                </span>

              </div>


              <strong className="yards">
                {player.yards}
              </strong>

            </div>
          )
        )}

      </div>

    </section>
  );
}


function HomePage() {
  const [
    dashboard,
    setDashboard
  ] = useState<DashboardData | null>(
    null
  );

  const [
    loading,
    setLoading
  ] = useState(true);

  const [
    error,
    setError
  ] = useState<string | null>(null);


  const [dashboardAttempt, setDashboardAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const loadDashboard = async () => {
      try {
        const apiBaseUrl = import.meta.env.VITE_API_BASE_URL;
        const response = await fetch(`${apiBaseUrl}/api/dashboard`, {
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Dashboard API returned ${response.status}`);
        }
        const data: DashboardData = await response.json();
        if (!controller.signal.aborted) setDashboard(data);
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : "Failed to load NFL analytics.");
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void loadDashboard();
    return () => controller.abort();
  }, [dashboardAttempt]);


  if (loading) {
    return (
      <main className="page centered">

        <h1>
          NFL Analytics
        </h1>

        <p>
          Loading analytics...
        </p>

      </main>
    );
  }


  if (error || !dashboard) {
    return (
      <main className="page centered">

        <h1>
          NFL Analytics
        </h1>

        <p className="error">
          {error ?? "No dashboard data."}
        </p>

        <button
          onClick={() => {
            setLoading(true);
            setError(null);
            setDashboardAttempt((attempt) => attempt + 1);
          }}
        >
          Try Again
        </button>

      </main>
    );
  }


  return (
    <main className="page">

      <header className="hero">

        <div>

          <p className="eyebrow">
            {dashboard.season} NFL SEASON
          </p>

          <h1>
            NFL Analytics
          </h1>

          <p className="subtitle">
            Advanced stats, efficiency metrics
            and league leaders powered by NFL
            play-by-play data.
          </p>

        </div>


        <div className="updated">

          <span>
            DATA UPDATED
          </span>

          <strong>
            {dashboard.snapshot_date}
          </strong>

        </div>

      </header>


      <MatchupAnalyzer />


      <LeagueRankings />


      <section className="dashboard-section">

        <div className="section-title">

          <div>

            <p className="eyebrow">
              TEAM ANALYTICS
            </p>

            <h2>
              Top Offenses
            </h2>

          </div>

          <span>
            EPA / Play
          </span>

        </div>


        <div className="power-grid">

          {dashboard.top_offenses.map(
            (team) => (

              <article
                className="team-card"
                key={team.team}
              >

                <div className="team-card-top">

                  <span className="team-rank">
                    #{team.rank}
                  </span>

                  <span className="team-code">
                    {team.team}
                  </span>

                </div>


                <div className="epa-number">
                  {formatEPA(
                    team.epa_per_play
                  )}
                </div>


                <span className="epa-label">
                  EPA / PLAY
                </span>


                <div className="team-stats">

                  <div>
                    <span>
                      Success
                    </span>

                    <strong>
                      {formatPercent(
                        team.success_rate
                      )}
                    </strong>
                  </div>


                  <div>
                    <span>
                      Pass EPA
                    </span>

                    <strong>
                      {formatEPA(
                        team.pass_epa_per_play
                      )}
                    </strong>
                  </div>


                  <div>
                    <span>
                      Rush EPA
                    </span>

                    <strong>
                      {formatEPA(
                        team.rush_epa_per_play
                      )}
                    </strong>
                  </div>

                </div>

              </article>
            )
          )}

        </div>

      </section>


      <section className="dashboard-section">

        <div className="section-title">

          <div>

            <p className="eyebrow">
              PLAYER STATS
            </p>

            <h2>
              League Leaders
            </h2>

          </div>

        </div>


        <div className="leader-grid">

          <LeaderList
            title="Passing"
            players={
              dashboard.leaders.passing
            }
          />

          <LeaderList
            title="Rushing"
            players={
              dashboard.leaders.rushing
            }
          />

          <LeaderList
            title="Receiving"
            players={
              dashboard.leaders.receiving
            }
          />

        </div>

      </section>


      <section className="dashboard-section">

        <div className="section-title">

          <div>

            <p className="eyebrow">
              LATEST RESULTS
            </p>

            <h2>
              Recent Games
            </h2>

          </div>

        </div>


        <div className="games-grid">

          {dashboard.recent_games.map(
            (game, index) => {

              const awayWon =
                game.away_score
                > game.home_score;

              const homeWon =
                game.home_score
                > game.away_score;


              return (
                <article
                  className="game-card"
                  key={
                    `${game.date}-`
                    + `${game.away_team}-`
                    + `${game.home_team}-`
                    + index
                  }
                >

                  <div className="game-meta">

                    <span>
                      Week {game.week}
                    </span>

                    <span>
                      {game.date}
                    </span>

                  </div>


                  <div className="score-row">

                    <span
                      className={
                        awayWon
                          ? "winner team-name"
                          : "team-name"
                      }
                    >
                      {game.away_team}
                    </span>

                    <strong
                      className={
                        awayWon
                          ? "winner"
                          : ""
                      }
                    >
                      {game.away_score}
                    </strong>

                  </div>


                  <div className="score-row">

                    <span
                      className={
                        homeWon
                          ? "winner team-name"
                          : "team-name"
                      }
                    >
                      {game.home_team}
                    </span>

                    <strong
                      className={
                        homeWon
                          ? "winner"
                          : ""
                      }
                    >
                      {game.home_score}
                    </strong>

                  </div>

                </article>
              );
            }
          )}

        </div>

      </section>

    </main>
  );
}


function App() {
  return (
    <>
    <nav className="app-navigation" aria-label="Main navigation">
      <Link to="/">Dashboard</Link>
      <Link to="/forecast">Game Forecasts <span>NEW</span></Link>
    </nav>
    <Routes>

      <Route path="/forecast" element={<GameForecast />} />

      <Route
        path="/"
        element={<HomePage />}
      />

      <Route
        path="/team/:teamCode"
        element={<TeamPage />}
      />

    </Routes>
    </>
  );
}


export default App;
