export interface Scoreline {
  home_score: number;
  away_score: number;
  probability: number;
  method?: string;
}

export function scorePresentation(projection?: Scoreline, exactScores: Scoreline[] = []) {
  const central = projection?.method === "minimum_expected_absolute_error";
  return {
    heading: central ? "Typical score estimate" : projection ? "Predicted final score" : "Expected average score",
    scoreKind: central ? "TYPICAL" : projection ? "PREDICTED" : "EXPECTED",
    exactProbabilityLabel: central
      ? "Probability of this exact typical score"
      : "Model probability of this exact score",
    alternativesHeading: central ? "Highest-probability exact scores" : "Next most likely scores",
    alternatives: (central ? exactScores : exactScores.filter((score) =>
      score.home_score !== projection?.home_score || score.away_score !== projection?.away_score,
    )).slice(0, 2),
    explanation: central
      ? "This is a typical score estimate, not the most likely exact final. It minimizes expected point error. The highest-probability exact scores are listed separately; each is still unlikely."
      : projection
        ? "The predicted final score is the model's highest-probability exact result; many other outcomes are possible."
        : "Scores are expected averages.",
    tiedProjection: central && projection.home_score === projection.away_score,
  };
}
