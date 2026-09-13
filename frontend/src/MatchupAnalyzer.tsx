import { useEffect, useState } from "react";

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

interface MatchupResponse {
  season: number;
  snapshot_date: string;
  team1: TeamAnalytics;
  team2: TeamAnalytics;
}

interface MetricRowProps {
  label: string;
  left: number | null;
  right: number | null;
  percent?: boolean;
  compare?: boolean;
}

function MetricRow({
  label,
  left,
  right,
  percent = false,
  compare = true,
}: MetricRowProps) {
  const format = (value: number | null) => {
    if (value === null) return "—";

    if (percent) {
      return `${(value * 100).toFixed(1)}%`;
    }

    return `${value >= 0 ? "+" : ""}${value.toFixed(3)}`;
  };

  const leftWins =
    compare &&
    left !== null &&
    right !== null &&
    left > right;

  const rightWins =
    compare &&
    left !== null &&
    right !== null &&
    right > left;

  return (
    <div className="comparison-row">
      <strong className={leftWins ? "metric-winner" : ""}>
        {format(left)}
      </strong>

      <span>{label}</span>

      <strong className={rightWins ? "metric-winner" : ""}>
        {format(right)}
      </strong>
    </div>
  );
}

export default function MatchupAnalyzer() {
  const [availableTeams, setAvailableTeams] =
    useState<TeamAnalytics[]>([]);

  const [team1, setTeam1] = useState("");
  const [team2, setTeam2] = useState("");

  const [matchup, setMatchup] =
    useState<MatchupResponse | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL;

  useEffect(() => {
    const loadTeams = async () => {
      try {
        const response = await fetch(
          `${apiBaseUrl}/api/team-analytics`
        );

        if (!response.ok) {
          throw new Error("Could not load teams.");
        }

        const data: TeamAnalytics[] =
          await response.json();

        const sorted = [...data].sort((a, b) =>
          a.team.localeCompare(b.team)
        );

        setAvailableTeams(sorted);

        if (sorted.length >= 2) {
          setTeam1(sorted[0].team);
          setTeam2(sorted[1].team);
        }
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Could not load teams."
        );
      }
    };

    loadTeams();
  }, [apiBaseUrl]);

  const compareTeams = async () => {
    if (!team1 || !team2) return;

    if (team1 === team2) {
      setError("Choose two different teams.");
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const response = await fetch(
        `${apiBaseUrl}/api/matchup?team1=${encodeURIComponent(
          team1
        )}&team2=${encodeURIComponent(team2)}`
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.error ?? "Matchup request failed."
        );
      }

      setMatchup(data);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to compare teams."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="dashboard-section">
      <div className="section-title">
        <div>
          <p className="eyebrow">MATCHUP ANALYZER</p>
          <h2>Compare Teams</h2>
        </div>
      </div>

      <div className="matchup-card">
        <div className="matchup-controls">
          <select
            value={team1}
            onChange={(event) =>
              setTeam1(event.target.value)
            }
          >
            {availableTeams.map((team) => (
              <option
                value={team.team}
                key={team.team}
              >
                {team.team}
              </option>
            ))}
          </select>

          <span className="versus">VS</span>

          <select
            value={team2}
            onChange={(event) =>
              setTeam2(event.target.value)
            }
          >
            {availableTeams.map((team) => (
              <option
                value={team.team}
                key={team.team}
              >
                {team.team}
              </option>
            ))}
          </select>

          <button
            onClick={compareTeams}
            disabled={loading}
          >
            {loading ? "Analyzing..." : "Compare"}
          </button>
        </div>

        {error && (
          <p className="matchup-error">{error}</p>
        )}

        {matchup && (
          <div className="comparison">
            <div className="comparison-heading">
              <div>
                <span>TEAM</span>
                <strong>{matchup.team1.team}</strong>
              </div>

              <div className="comparison-date">
                Offensive comparison
                <small>
                  Data through {matchup.snapshot_date}
                </small>
              </div>

              <div>
                <span>TEAM</span>
                <strong>{matchup.team2.team}</strong>
              </div>
            </div>

            <MetricRow
              label="EPA / Play"
              left={matchup.team1.epa_per_play}
              right={matchup.team2.epa_per_play}
            />

            <MetricRow
              label="Success Rate"
              left={matchup.team1.success_rate}
              right={matchup.team2.success_rate}
              percent
            />

            <MetricRow
              label="Pass EPA"
              left={matchup.team1.pass_epa_per_play}
              right={matchup.team2.pass_epa_per_play}
            />

            <MetricRow
              label="Rush EPA"
              left={matchup.team1.rush_epa_per_play}
              right={matchup.team2.rush_epa_per_play}
            />

            <MetricRow
              label="Explosive Rate"
              left={matchup.team1.explosive_play_rate}
              right={matchup.team2.explosive_play_rate}
              percent
            />

            <MetricRow
              label="Pass Rate"
              left={matchup.team1.pass_rate}
              right={matchup.team2.pass_rate}
              percent
              compare={false}
            />
          </div>
        )}
      </div>
    </section>
  );
}