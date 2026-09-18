import { createContext, useContext } from "react";

export interface TeamAnalytics {
  season: number;
  snapshot_date: string;
  team: string;
  plays: number | null;
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

export const TeamAnalyticsContext = createContext<{
  teams: TeamAnalytics[]; loading: boolean; error: string | null; retry: () => void;
} | null>(null);

export function useTeamAnalytics() {
  const value = useContext(TeamAnalyticsContext);
  if (!value) throw new Error("Team analytics requires its provider.");
  return value;
}
