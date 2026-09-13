import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";


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


interface RankedTeam extends TeamAnalytics {
  offense_rank: number;
  defense_rank: number;
  overall_rank: number;
  overall_score: number;
}


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
  const [
    teams,
    setTeams
  ] = useState<TeamAnalytics[]>([]);

  const [
    mode,
    setMode
  ] = useState<RankingMode>("overall");

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
    const loadRankings = async () => {
      try {
        setLoading(true);
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

        setTeams(data);

      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to load rankings."
        );
      } finally {
        setLoading(false);
      }
    };

    loadRankings();

  }, [apiBaseUrl]);


  const rankedTeams =
    useMemo(() => {
      if (teams.length === 0) {
        return [];
      }

      const offenseSorted = [
        ...teams
      ].sort((a, b) => {
        if (
          a.epa_per_play === null
          && b.epa_per_play === null
        ) {
          return 0;
        }

        if (a.epa_per_play === null) {
          return 1;
        }

        if (b.epa_per_play === null) {
          return -1;
        }

        return (
          b.epa_per_play
          - a.epa_per_play
        );
      });


      const defenseSorted = [
        ...teams
      ].sort((a, b) => {
        if (
          a.def_epa_per_play === null
          && b.def_epa_per_play === null
        ) {
          return 0;
        }

        if (
          a.def_epa_per_play === null
        ) {
          return 1;
        }

        if (
          b.def_epa_per_play === null
        ) {
          return -1;
        }

        return (
          a.def_epa_per_play
          - b.def_epa_per_play
        );
      });


      const offenseRanks =
        new Map<string, number>();

      offenseSorted.forEach(
        (team, index) => {
          offenseRanks.set(
            team.team,
            index + 1
          );
        }
      );


      const defenseRanks =
        new Map<string, number>();

      defenseSorted.forEach(
        (team, index) => {
          defenseRanks.set(
            team.team,
            index + 1
          );
        }
      );


      const combined = teams.map(
        (team) => {
          const offenseRank =
            offenseRanks.get(
              team.team
            ) ?? teams.length;

          const defenseRank =
            defenseRanks.get(
              team.team
            ) ?? teams.length;

          const overallScore =
            (
              offenseRank
              + defenseRank
            ) / 2;

          return {
            ...team,

            offense_rank:
              offenseRank,

            defense_rank:
              defenseRank,

            overall_rank: 0,

            overall_score:
              overallScore
          };
        }
      );


      combined.sort(
        (a, b) =>
          a.overall_score
          - b.overall_score
      );


      combined.forEach(
        (team, index) => {
          team.overall_rank =
            index + 1;
        }
      );


      return combined;

    }, [teams]);


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
            Overall rank is currently a simple average
            of offensive rank and defensive rank.
          </p>
        )}

      </div>

    </section>
  );
}


export default LeagueRankings;