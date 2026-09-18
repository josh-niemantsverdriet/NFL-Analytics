import { useMemo, useState } from "react";
import { Link } from "react-router";
import { useTeamAnalytics } from "./teamAnalytics";
import { rankTeams } from "./rankings";
import type { RankedTeam } from "./rankings";


type RankingMode =
  | "overall"
  | "offense"
  | "defense";


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


function LeagueRankings() {
  const { teams, loading, error, retry } = useTeamAnalytics();

  const [
    mode,
    setMode
  ] = useState<RankingMode>("overall");

  const rankedTeams = useMemo(() => rankTeams(teams), [teams]);

  const displayedTeams =
    useMemo(() => {
      const copy = [
        ...rankedTeams
      ];

      if (mode === "offense") {
        return copy.sort(
          (a, b) =>
            a.offense_rank
            - b.offense_rank
        );
      }

      if (mode === "defense") {
        return copy.sort(
          (a, b) =>
            a.defense_rank
            - b.defense_rank
        );
      }

      return copy.sort(
        (a, b) =>
          a.overall_rank
          - b.overall_rank
      );

    }, [
      rankedTeams,
      mode
    ]);


  const getRank = (
    team: RankedTeam
  ) => {
    if (mode === "offense") {
      return team.offense_rank;
    }

    if (mode === "defense") {
      return team.defense_rank;
    }

    return team.overall_rank;
  };


  if (loading) {
    return (
      <section className="dashboard-section">
        <p className="matchup-status">
          Loading league rankings...
        </p>
      </section>
    );
  }


  if (error) {
    return (
      <section className="dashboard-section">
        <p className="matchup-error">
          {error}
          <button onClick={retry}>Retry team data</button>
        </p>
      </section>
    );
  }


  return (
    <section className="dashboard-section">

      <div className="section-title">

        <div>
          <p className="eyebrow">
            LEAGUE RANKINGS
          </p>

          <h2>
            Team Rankings
          </h2>
        </div>

      </div>


      <div className="ranking-tabs">

        <button
          className={
            mode === "overall"
              ? "ranking-tab active"
              : "ranking-tab"
          }
          aria-pressed={mode === "overall"}
          onClick={() =>
            setMode("overall")
          }
        >
          Overall
        </button>


        <button
          className={
            mode === "offense"
              ? "ranking-tab active"
              : "ranking-tab"
          }
          aria-pressed={mode === "offense"}
          onClick={() =>
            setMode("offense")
          }
        >
          Offense
        </button>


        <button
          className={
            mode === "defense"
              ? "ranking-tab active"
              : "ranking-tab"
          }
          aria-pressed={mode === "defense"}
          onClick={() =>
            setMode("defense")
          }
        >
          Defense
        </button>

      </div>


      <div className="rankings-card">

        <div className="rankings-table-wrapper">

          <table className="rankings-table">

            <thead>

              {mode === "overall" && (
                <tr>
                  <th>Rank</th>
                  <th>Team</th>
                  <th>Off Rank</th>
                  <th>Def Rank</th>
                  <th>Off EPA</th>
                  <th>Def EPA Allowed</th>
                </tr>
              )}


              {mode === "offense" && (
                <tr>
                  <th>Rank</th>
                  <th>Team</th>
                  <th>EPA / Play</th>
                  <th>Pass EPA</th>
                  <th>Rush EPA</th>
                  <th>Success Rate</th>
                </tr>
              )}


              {mode === "defense" && (
                <tr>
                  <th>Rank</th>
                  <th>Team</th>
                  <th>EPA Allowed</th>
                  <th>Pass EPA Allowed</th>
                  <th>Rush EPA Allowed</th>
                  <th>Success Allowed</th>
                </tr>
              )}

            </thead>


            <tbody>

              {displayedTeams.map(
                (team) => (

                  <tr
                    key={team.team}
                    className={
                      getRank(team) <= 3
                        ? "top-ranked-team"
                        : ""
                    }
                  >

                    <td className="ranking-number">
                      #{getRank(team)}
                    </td>


                    <td className="ranking-team">

                      <Link
                        to={`/team/${team.team}`}
                        style={{
                          color: "inherit",
                          textDecoration: "none"
                        }}
                      >
                        {team.team}
                      </Link>

                    </td>


                    {mode === "overall" && (
                      <>
                        <td>
                          #{team.offense_rank}
                        </td>

                        <td>
                          #{team.defense_rank}
                        </td>

                        <td>
                          {formatEPA(
                            team.epa_per_play
                          )}
                        </td>

                        <td>
                          {formatEPA(
                            team.def_epa_per_play
                          )}
                        </td>
                      </>
                    )}


                    {mode === "offense" && (
                      <>
                        <td>
                          {formatEPA(
                            team.epa_per_play
                          )}
                        </td>

                        <td>
                          {formatEPA(
                            team.pass_epa_per_play
                          )}
                        </td>

                        <td>
                          {formatEPA(
                            team.rush_epa_per_play
                          )}
                        </td>

                        <td>
                          {formatPercent(
                            team.success_rate
                          )}
                        </td>
                      </>
                    )}


                    {mode === "defense" && (
                      <>
                        <td>
                          {formatEPA(
                            team.def_epa_per_play
                          )}
                        </td>

                        <td>
                          {formatEPA(
                            team.def_pass_epa_per_play
                          )}
                        </td>

                        <td>
                          {formatEPA(
                            team.def_rush_epa_per_play
                          )}
                        </td>

                        <td>
                          {formatPercent(
                            team.def_success_rate_allowed
                          )}
                        </td>
                      </>
                    )}

                  </tr>
                )
              )}

            </tbody>

          </table>

        </div>


        {mode === "overall" && (
          <p className="ranking-note">
            Overall rank averages offensive and defensive ranks. Equal metrics share a rank; this is a descriptive ranking, not a forecast.
          </p>
        )}

      </div>

    </section>
  );
}


export default LeagueRankings;