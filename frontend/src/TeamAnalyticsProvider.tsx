import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { fetchData } from "./api";
import { TeamAnalyticsContext } from "./teamAnalytics";
import type { TeamAnalytics } from "./teamAnalytics";

export default function TeamAnalyticsProvider({ children }: { children: ReactNode }) {
  const [teams, setTeams] = useState<TeamAnalytics[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    fetchData<TeamAnalytics[]>("/api/team-analytics", controller.signal)
      .then((data) => { if (!controller.signal.aborted) setTeams([...data].sort((a, b) => a.team.localeCompare(b.team))); })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "Unable to load team analytics.");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [attempt]);
  function retry() {
    setLoading(true);
    setError(null);
    setAttempt((value) => value + 1);
  }
  return <TeamAnalyticsContext.Provider value={{ teams, loading, error, retry }}>{children}</TeamAnalyticsContext.Provider>;
}
