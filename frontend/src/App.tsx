import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router";

import "./App.css";

import LeagueRankings from "./LeagueRankings";
import MatchupAnalyzer from "./MatchupAnalyzer";
import TeamPage from "./TeamPage";
import GameForecast from "./GameForecast";
import TeamAnalyticsProvider from "./TeamAnalyticsProvider";
import { fetchData } from "./api";


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


  leaders: {
    passing: PlayerLeader[];
    rushing: PlayerLeader[];
    receiving: PlayerLeader[];
  };

  recent_games: Game[];
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
        const data = await fetchData<DashboardData>("/api/dashboard", controller.signal);
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
      <main id="main-content" className="page centered">

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
      <main id="main-content" className="page centered">

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
    <main id="main-content" className="page">

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
    <a className="skip-link" href="#main-content">Skip to content</a>
    <nav className="app-navigation" aria-label="Main navigation">
      <NavLink to="/" end>Dashboard</NavLink>
      <NavLink to="/forecast">Game Forecasts</NavLink>
    </nav>
    <Routes>

      <Route path="/forecast" element={<GameForecast />} />

      <Route
        path="/"
        element={<TeamAnalyticsProvider><HomePage /></TeamAnalyticsProvider>}
      />

      <Route
        path="/team/:teamCode"
        element={<TeamPage />}
      />

      <Route path="*" element={<main id="main-content" className="page"><h1>Page not found</h1><NavLink to="/">Back to dashboard</NavLink></main>} />
    </Routes>
    </>
  );
}


export default App;
