import type { TeamAnalytics } from "./teamAnalytics";

export interface RankedTeam extends TeamAnalytics {
  offense_rank: number;
  defense_rank: number;
  overall_rank: number;
  overall_score: number;
}

// Competition ranks match SQL RANK(): ties share a rank and leave a gap.
function ranks(teams: TeamAnalytics[], metric: (team: TeamAnalytics) => number | null, descending = false) {
  const sorted = [...teams].sort((a, b) => {
    const left = metric(a), right = metric(b);
    if (left == null && right == null) return a.team.localeCompare(b.team);
    if (left == null) return 1;
    if (right == null) return -1;
    return (descending ? right - left : left - right) || a.team.localeCompare(b.team);
  });
  const result = new Map<string, number>();
  let rank = 1;
  sorted.forEach((team, index) => {
    if (index === 0 || metric(team) !== metric(sorted[index - 1])) rank = index + 1;
    result.set(team.team, rank);
  });
  return result;
}

export function rankTeams(teams: TeamAnalytics[]): RankedTeam[] {
  const offense = ranks(teams, (team) => team.epa_per_play, true);
  const defense = ranks(teams, (team) => team.def_epa_per_play);
  const combined = teams.map((team) => ({
    ...team, offense_rank: offense.get(team.team)!, defense_rank: defense.get(team.team)!,
    overall_score: (offense.get(team.team)! + defense.get(team.team)!) / 2,
    overall_rank: 0,
  }));
  const scores = new Map(combined.map((team) => [team.team, team.overall_score]));
  const overall = ranks(teams, (team) => scores.get(team.team)!);
  return combined.map((team) => ({ ...team, overall_rank: overall.get(team.team)! }))
    .sort((a, b) => a.overall_rank - b.overall_rank || a.team.localeCompare(b.team));
}
