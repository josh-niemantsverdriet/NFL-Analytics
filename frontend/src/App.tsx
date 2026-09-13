import { useEffect, useState } from "react";
import "./App.css";

interface TeamAnalytics {
  season: number;
  snapshot_date: string;
  team: string;
  plays: number;
  epa_per_play: number | null;
  pass_epa_per_play: number | null;
  rush_epa_per_play: number | null;
  success_rate: number | null;
  explosive_play_rate: number | null;
  pass_rate: number | null;
}

function App() {
  const [teams, setTeams] = useState<TeamAnalytics[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        const apiBaseUrl = import.meta.env.VITE_API_BASE_URL;

        const response = await fetch(
          `${apiBaseUrl}/api/team-analytics`
        );

        if (!response.ok) {
          throw new Error(`API returned ${response.status}`);
        }

        const data: TeamAnalytics[] = await response.json();
        setTeams(data);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load data"
        );
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, []);

  const formatNumber = (value: number | null) =>
    value === null ? "—" : value.toFixed(3);

  const formatPercent = (value: number | null) =>
    value === null ? "—" : `${(value * 100).toFixed(1)}%`;

  if (loading) {
    return <main className="page">Loading NFL analytics...</main>;
  }

  if (error) {
    return (
      <main className="page">
        <h1>NFL Analytics</h1>
        <p className="error">{error}</p>
      </main>
    );
  }

  return (
    <main className="page">
      <header className="hero">
        <div>
          <p className="eyebrow">2026 NFL SEASON</p>
          <h1>NFL Analytics</h1>
          <p className="subtitle">
            Advanced team metrics from NFL play-by-play data.
          </p>
        </div>

        {teams.length > 0 && (
          <div className="snapshot">
            Latest snapshot
            <strong>{teams[0].snapshot_date}</strong>
          </div>
        )}
      </header>

      <section className="card">
        <div className="section-header">
          <h2>Offensive Efficiency</h2>
          <p>Ranked by EPA per play</p>
        </div>

        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Rank</th>
                <th>Team</th>
                <th>Plays</th>
                <th>EPA / Play</th>
                <th>Pass EPA</th>
                <th>Rush EPA</th>
                <th>Success Rate</th>
                <th>Explosive Rate</th>
                <th>Pass Rate</th>
              </tr>
            </thead>

            <tbody>
              {teams.map((team, index) => (
                <tr key={team.team}>
                  <td>{index + 1}</td>
                  <td className="team">{team.team}</td>
                  <td>{team.plays}</td>
                  <td>{formatNumber(team.epa_per_play)}</td>
                  <td>{formatNumber(team.pass_epa_per_play)}</td>
                  <td>{formatNumber(team.rush_epa_per_play)}</td>
                  <td>{formatPercent(team.success_rate)}</td>
                  <td>{formatPercent(team.explosive_play_rate)}</td>
                  <td>{formatPercent(team.pass_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

export default App;