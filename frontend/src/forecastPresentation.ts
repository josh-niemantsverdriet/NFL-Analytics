export interface Scoreline {
  home_score: number;
  away_score: number;
  probability: number;
  method?: string;
}

export function scorePresentation(projection?: Scoreline, exactScores: Scoreline[] = []) {
  const central = projection?.method === "minimum_expected_absolute_error";
  return {
    heading: central ? "Projected score" : projection ? "Predicted final score" : "Expected average score",
    alternativesHeading: central ? "Most likely exact scores" : "Next most likely scores",
    alternatives: (central ? exactScores : exactScores.filter((score) =>
      score.home_score !== projection?.home_score || score.away_score !== projection?.away_score,
    )).slice(0, 2),
    explanation: central
      ? "This central score estimate minimizes expected point error. Most likely exact scores are separate outcomes, each with a small probability."
      : projection
        ? "The predicted final score is the model’s most likely single result; many other outcomes are possible."
        : "Scores are expected averages.",
    tiedProjection: central && projection.home_score === projection.away_score,
  };
}
