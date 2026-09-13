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

  def_plays: number | null;
  def_epa_per_play: number | null;
  def_pass_epa_per_play: number | null;
  def_rush_epa_per_play: number | null;
  def_success_rate_allowed: number | null;
  def_explosive_play_rate_allowed: number | null;
}

interface Projection {
  team: string;
  opponent: string;

  expected_epa_per_play: number | null;
  expected_pass_epa_per_play: number | null;
  expected_rush_epa_per_play: number | null;
  expected_success_rate: number | null;
  expected_explosive_rate: number | null;
}

interface MatchupResponse {
  season: number;
  snapshot_date: string;

  team1: TeamAnalytics;
  team2: TeamAnalytics;

  team1_projection: Projection;
  team2_projection: Projection;

  matchup_advantage: {
    team: string | null;
    epa_per_play_edge: number | null;
  };

  method: string;
}

interface MetricRowProps {
  label: string;
  left: number | null;
  right: number | null;
  percent?: boolean;
  lowerIsBetter?: boolean;
}

function MetricRow({
  label,
  left,
  right,
  percent = false,
  lowerIsBetter = false,
}: MetricRowProps) {
  const formatValue = (
    value: number | null
  ) => {
    if (value === null) {
      return "—";
    }

    if (percent) {
      return `${(value * 100).toFixed(1)}%`;
    }

    return `${value >= 0 ? "+" : ""}${value.toFixed(3)}`;
  };

  let leftWins = false;
  let rightWins = false;

  if (
    left !== null
    && right !== null
    && left !== right
  ) {
    if (lowerIsBetter) {
      leftWins = left < right;
      rightWins = right < left;
    } else {
      leftWins = left > right;
      rightWins = right > left;
    }
  }

  return (
    <div className="comparison-row">
      <strong
        className={
          leftWins
            ? "metric-winner"
            : ""
        }
      >
        {formatValue(left)}
      </strong>

      <span>{label}</span>

      <strong
        className={
          rightWins
            ? "metric-winner"
            : ""
        }
      >
        {formatValue(right)}
      </strong>
    </div>
  );
}


function MatchupAnalyzer() {
  const [
    availableTeams,
    setAvailableTeams
  ] = useState<TeamAnalytics[]>([]);

  const [
    team1,
    setTeam1
  ] = useState("");

  const [
    team2,
    setTeam2
  ] = useState("");

  const [
    matchup,
    setMatchup
  ] = useState<MatchupResponse | null>(
    null
  );

  const [
    loadingTeams,
    setLoadingTeams
  ] = useState(true);

  const [
    loadingMatchup,
    setLoadingMatchup
  ] = useState(false);

  const [
    error,
    setError
  ] = useState<string | null>(null);

  const apiBaseUrl =
    import.meta.env.VITE_API_BASE_URL;


  useEffect(() => {
    const loadTeams = async () => {
      try {
        setLoadingTeams(true);
        setError(null);

        const response = await fetch(
          `${apiBaseUrl}/api/team-analytics`
        );

        if (!response.ok) {
          throw new Error(
            `Team API returned ${response.status}`
          );
        }

        const data: TeamAnalytics[] =
          await response.json();

        const sortedTeams = [
          ...data
        ].sort(
          (a, b) =>
            a.team.localeCompare(
              b.team
            )
        );

        setAvailableTeams(
          sortedTeams
        );

        if (
          sortedTeams.length >= 2
        ) {
          setTeam1(
            sortedTeams[0].team
          );

          setTeam2(
            sortedTeams[1].team
          );
        }
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Could not load teams."
        );
      } finally {
        setLoadingTeams(false);
      }
    };

    loadTeams();
  }, [apiBaseUrl]);


  const compareTeams = async () => {
    if (!team1 || !team2) {
      setError(
        "Choose two teams."
      );
      return;
    }

    if (team1 === team2) {
      setError(
        "Choose two different teams."
      );
      return;
    }

    try {
      setLoadingMatchup(true);
      setError(null);

      const url =
        `${apiBaseUrl}/api/matchup`
        + `?team1=${encodeURIComponent(
          team1
        )}`
        + `&team2=${encodeURIComponent(
          team2
        )}`;

      const response = await fetch(
        url
      );

      const data =
        await response.json();

      if (!response.ok) {
        throw new Error(
          data.error
          ?? `Matchup API returned ${response.status}`
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
      setLoadingMatchup(false);
    }
  };


  return (
    <section className="dashboard-section">
      <div className="section-title">
        <div>
          <p className="eyebrow">
            MATCHUP ANALYZER
          </p>

          <h2>
            Offense vs Defense
          </h2>
        </div>
      </div>

      <div className="matchup-card">

        {loadingTeams ? (
          <p className="matchup-status">
            Loading teams...
          </p>
        ) : (
          <div className="matchup-controls">

            <select
              value={team1}
              onChange={(event) =>
                setTeam1(
                  event.target.value
                )
              }
            >
              {availableTeams.map(
                (team) => (
                  <option
                    key={team.team}
                    value={team.team}
                  >
                    {team.team}
                  </option>
                )
              )}
            </select>

            <span className="versus">
              VS
            </span>

            <select
              value={team2}
              onChange={(event) =>
                setTeam2(
                  event.target.value
                )
              }
            >
              {availableTeams.map(
                (team) => (
                  <option
                    key={team.team}
                    value={team.team}
                  >
                    {team.team}
                  </option>
                )
              )}
            </select>

            <button
              onClick={compareTeams}
              disabled={
                loadingMatchup
              }
            >
              {loadingMatchup
                ? "Analyzing..."
                : "Compare"}
            </button>

          </div>
        )}


        {error && (
          <p className="matchup-error">
            {error}
          </p>
        )}


        {matchup && (
          <div className="comparison">

            <div className="comparison-heading">

              <div>
                <span>
                  OFFENSE
                </span>

                <strong>
                  {
                    matchup.team1.team
                  }
                </strong>
              </div>

              <div className="comparison-date">

                Matchup efficiency

                <small>
                  Data through{" "}
                  {
                    matchup.snapshot_date
                  }
                </small>

                {matchup
                  .matchup_advantage
                  .team && (
                  <small>
                    Efficiency edge:{" "}
                    {
                      matchup
                        .matchup_advantage
                        .team
                    }
                  </small>
                )}

              </div>

              <div>
                <span>
                  OFFENSE
                </span>

                <strong>
                  {
                    matchup.team2.team
                  }
                </strong>
              </div>

            </div>


            <MetricRow
              label="Projected EPA / Play"
              left={
                matchup
                  .team1_projection
                  .expected_epa_per_play
              }
              right={
                matchup
                  .team2_projection
                  .expected_epa_per_play
              }
            />


            <MetricRow
              label="Projected Pass EPA"
              left={
                matchup
                  .team1_projection
                  .expected_pass_epa_per_play
              }
              right={
                matchup
                  .team2_projection
                  .expected_pass_epa_per_play
              }
            />


            <MetricRow
              label="Projected Rush EPA"
              left={
                matchup
                  .team1_projection
                  .expected_rush_epa_per_play
              }
              right={
                matchup
                  .team2_projection
                  .expected_rush_epa_per_play
              }
            />


            <MetricRow
              label="Projected Success Rate"
              left={
                matchup
                  .team1_projection
                  .expected_success_rate
              }
              right={
                matchup
                  .team2_projection
                  .expected_success_rate
              }
              percent
            />


            <MetricRow
              label="Projected Explosive Rate"
              left={
                matchup
                  .team1_projection
                  .expected_explosive_rate
              }
              right={
                matchup
                  .team2_projection
                  .expected_explosive_rate
              }
              percent
            />


            <div className="comparison-heading">

              <div>
                <span>
                  {
                    matchup.team1.team
                  }
                </span>

                <strong>
                  Offense
                </strong>
              </div>

              <div className="comparison-date">
                Raw efficiency
              </div>

              <div>
                <span>
                  {
                    matchup.team2.team
                  }
                </span>

                <strong>
                  Offense
                </strong>
              </div>

            </div>


            <MetricRow
              label="Offensive EPA / Play"
              left={
                matchup
                  .team1
                  .epa_per_play
              }
              right={
                matchup
                  .team2
                  .epa_per_play
              }
            />


            <MetricRow
              label="Pass EPA"
              left={
                matchup
                  .team1
                  .pass_epa_per_play
              }
              right={
                matchup
                  .team2
                  .pass_epa_per_play
              }
            />


            <MetricRow
              label="Rush EPA"
              left={
                matchup
                  .team1
                  .rush_epa_per_play
              }
              right={
                matchup
                  .team2
                  .rush_epa_per_play
              }
            />


            <div className="comparison-heading">

              <div>
                <span>
                  {
                    matchup.team1.team
                  }
                </span>

                <strong>
                  Defense
                </strong>
              </div>

              <div className="comparison-date">
                Lower is better
              </div>

              <div>
                <span>
                  {
                    matchup.team2.team
                  }
                </span>

                <strong>
                  Defense
                </strong>
              </div>

            </div>


            <MetricRow
              label="EPA / Play Allowed"
              left={
                matchup
                  .team1
                  .def_epa_per_play
              }
              right={
                matchup
                  .team2
                  .def_epa_per_play
              }
              lowerIsBetter
            />


            <MetricRow
              label="Pass EPA Allowed"
              left={
                matchup
                  .team1
                  .def_pass_epa_per_play
              }
              right={
                matchup
                  .team2
                  .def_pass_epa_per_play
              }
              lowerIsBetter
            />


            <MetricRow
              label="Rush EPA Allowed"
              left={
                matchup
                  .team1
                  .def_rush_epa_per_play
              }
              right={
                matchup
                  .team2
                  .def_rush_epa_per_play
              }
              lowerIsBetter
            />


            <MetricRow
              label="Success Rate Allowed"
              left={
                matchup
                  .team1
                  .def_success_rate_allowed
              }
              right={
                matchup
                  .team2
                  .def_success_rate_allowed
              }
              percent
              lowerIsBetter
            />


            <MetricRow
              label="Explosive Rate Allowed"
              left={
                matchup
                  .team1
                  .def_explosive_play_rate_allowed
              }
              right={
                matchup
                  .team2
                  .def_explosive_play_rate_allowed
              }
              percent
              lowerIsBetter
            />


            <p className="matchup-status">
              {matchup.method}
            </p>

          </div>
        )}

      </div>
    </section>
  );
}


export default MatchupAnalyzer;