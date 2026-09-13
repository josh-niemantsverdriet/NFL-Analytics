import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router";
import "./GameForecast.css";

interface Forecast {
  home_team: string;
  away_team: string;
  neutral: boolean;
  home_score: number;
  away_score: number;
  home_win_probability: number;
  away_win_probability: number;
  favorite: string | null;
  margin: number;
  total: number;
  margin_interval: { low: number; high: number; coverage: number };
  home_games: number;
  away_games: number;
}

interface ModelInfo {
  name: string;
  training_games: number;
  trained_through: string;
  history_seasons: number[];
  evaluation: {
    games: number;
    from_date: string | null;
    through_date: string | null;
    margin_mae: number | null;
    winner_accuracy: number | null;
    home_baseline_accuracy: number | null;
    brier_score: number | null;
    margin_interval_coverage?: number | null;
    decisive_games?: number;
  };
  limitations: string[];
  method: string;
}

interface ForecastResponse {
  generated_at: string;
  data_cutoff: string;
  model: ModelInfo;
  forecast: Forecast;
}

interface UpcomingGame {
  game_id: string;
  season: number;
  week: number;
  date: string;
  home_team: string;
  away_team: string;
  neutral: boolean;
  forecast: Forecast;
}

interface ScheduleResponse {
  generated_at: string;
  data_cutoff: string;
  teams: string[];
  games: UpcomingGame[];
  model: ModelInfo;
}

interface MatchupRequest {
  home_team: string;
  away_team: string;
  neutral: boolean;
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

function percent(value: number | null) {
  return value === null ? "Unavailable" : `${(value * 100).toFixed(1)}%`;
}

function dateLabel(value: string | null) {
  if (!value) return "Unavailable";
  // Keep date-only schedule values on their original calendar day in every timezone.
  const date = new Date(`${value.slice(0, 10)}T12:00:00Z`);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        timeZone: "UTC",
      });
}

function signedPoints(value: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}`;
}

async function fetchData<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    let message = `Forecast service returned ${response.status}. Please try again.`;
    try {
      const body: { error?: string } = await response.json();
      if (body.error) message = body.error;
    } catch {
      // An unavailable service can return HTML instead of an API error.
    }
    throw new Error(message);
  }
  return response.json();
}

function Scoreboard({ result, game }: { result: ForecastResponse; game?: UpcomingGame }) {
  const forecast = result.forecast;
  const margin = Math.abs(forecast.margin);
  return (
    <section className="forecast-board" aria-labelledby="forecast-result-title">
      <div className="forecast-board-top">
        <h2 id="forecast-result-title">Projected matchup</h2>
        <span>
          {game ? `Week ${game.week} · ${dateLabel(game.date)}` : "Your matchup"}
          {forecast.neutral ? " · Neutral field" : ""}
        </span>
      </div>

      <div className="forecast-scoreboard">
        <div className="forecast-team forecast-away">
          <span className="forecast-team-location">{forecast.neutral ? "Team 1" : "Away"}</span>
          <h3>{forecast.away_team}</h3>
          <strong className="forecast-score">{forecast.away_score.toFixed(1)}</strong>
          <span className="forecast-team-sample">{forecast.away_games} games of team history</span>
        </div>
        <div className="forecast-score-divider" aria-hidden="true">
          <span>PROJECTED</span>
          <strong>:</strong>
          <span>POINTS</span>
        </div>
        <div className="forecast-team forecast-home">
          <span className="forecast-team-location">{forecast.neutral ? "Team 2" : "Home"}</span>
          <h3>{forecast.home_team}</h3>
          <strong className="forecast-score">{forecast.home_score.toFixed(1)}</strong>
          <span className="forecast-team-sample">{forecast.home_games} games of team history</span>
        </div>
      </div>

      <div className="forecast-probability">
        <div className="forecast-probability-labels">
          <span className="forecast-away-color"><strong>{forecast.away_team}</strong> {percent(forecast.away_win_probability)}</span>
          <span className="forecast-probability-caption">WIN CHANCE</span>
          <span className="forecast-home-color"><strong>{forecast.home_team}</strong> {percent(forecast.home_win_probability)}</span>
        </div>
        <div className="forecast-probability-bar" aria-hidden="true">
          <span className="forecast-probability-away" style={{ width: `${forecast.away_win_probability * 100}%` }} />
          <span className="forecast-probability-home" style={{ width: `${forecast.home_win_probability * 100}%` }} />
        </div>
        <p className="forecast-favorite">
          {forecast.favorite
            ? <><strong>{forecast.favorite}</strong> has the edge by {margin.toFixed(1)} projected points.</>
            : "Too close to call: the model projects an even matchup."}
        </p>
      </div>

      <div className="forecast-insights">
        <div>
          <span>Projected total</span>
          <strong>{forecast.total.toFixed(1)} <small>points</small></strong>
        </div>
        <div>
          <span>{Math.round(forecast.margin_interval.coverage * 100)}% model range for {forecast.home_team} margin</span>
          <strong>{signedPoints(forecast.margin_interval.low)} <small>to</small> {signedPoints(forecast.margin_interval.high)}</strong>
          <small>Negative means {forecast.away_team} ahead; positive means {forecast.home_team} ahead.</small>
        </div>
      </div>
      <p className="forecast-board-note">
        Scores are expected averages. Win chances are model estimates with ties excluded; individual games can land well outside the projection.
      </p>
    </section>
  );
}

function ModelDetails({ model, cutoff }: { model: ModelInfo; cutoff: string }) {
  const evaluation = model.evaluation;
  return (
    <details className="forecast-method">
      <summary>How the forecast works <span>Method & track record</span></summary>
      <div className="forecast-method-content">
        <h3>{model.name}</h3>
        <p>{model.method}</p>
        <p>
          Trained on {model.training_games.toLocaleString()} games from {model.history_seasons.join(", ")},
          through {dateLabel(model.trained_through)}. Results on or after {dateLabel(cutoff)} are excluded.
        </p>
        <h3>Tested on games it had not seen</h3>
        {evaluation.games > 0 ? (
          <>
            <p>
              {evaluation.games.toLocaleString()} games from {dateLabel(evaluation.from_date)} to {dateLabel(evaluation.through_date)}.
              This historical test is a useful check, not a promise of future accuracy.
            </p>
            <p>
              For this test, a model trained only on earlier results was kept unchanged throughout the test dates.
              The forecasts above use a model trained again with all available history before the cutoff.
            </p>
            <dl className="forecast-evaluation">
              <div><dt>Correct winner{evaluation.decisive_games !== undefined ? ` · ${evaluation.decisive_games.toLocaleString()} games` : ""}</dt><dd>{percent(evaluation.winner_accuracy)}</dd></div>
              <div><dt>Always picking home</dt><dd>{percent(evaluation.home_baseline_accuracy)}</dd></div>
              <div><dt>Average margin error</dt><dd>{evaluation.margin_mae === null ? "Unavailable" : `${evaluation.margin_mae.toFixed(1)} pts`}</dd></div>
              <div><dt>Probability error (Brier score)</dt><dd>{evaluation.brier_score === null ? "Unavailable" : evaluation.brier_score.toFixed(3)}</dd></div>
            </dl>
            <p className="forecast-small">Winner accuracy excludes tied games. Lower margin and probability errors are better.</p>
            {evaluation.margin_interval_coverage != null && <p>
              The 80% model margin ranges contained the actual margin in {percent(evaluation.margin_interval_coverage)} of the {evaluation.games.toLocaleString()} test games.
              Observed coverage can differ from the model’s target.
            </p>}
          </>
        ) : (
          <p>There are not enough historical games to report a separate accuracy test yet.</p>
        )}
        {model.limitations.length > 0 && <><h3>What to keep in mind</h3><ul>{model.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></>}
      </div>
    </details>
  );
}

export default function GameForecast() {
  const [schedule, setSchedule] = useState<ScheduleResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [homeTeam, setHomeTeam] = useState("");
  const [awayTeam, setAwayTeam] = useState("");
  const [neutral, setNeutral] = useState(false);
  const [result, setResult] = useState<ForecastResponse | null>(null);
  const [selectedGameId, setSelectedGameId] = useState<string | null>(null);
  const [predicting, setPredicting] = useState(false);
  const [predictionError, setPredictionError] = useState<string | null>(null);
  const predictionController = useRef<AbortController | null>(null);
  const lastRequest = useRef<MatchupRequest | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchData<ScheduleResponse>(`${API_BASE}/api/forecasts`, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setSchedule(data);
        const firstGame = data.games[0];
        setHomeTeam(firstGame?.home_team ?? data.teams[0] ?? "");
        setAwayTeam(firstGame?.away_team ?? data.teams[1] ?? "");
        setNeutral(firstGame?.neutral ?? false);
        setSelectedGameId(firstGame?.game_id ?? null);
        setResult(firstGame ? { ...data, forecast: firstGame.forecast } : null);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setLoadError(error instanceof Error ? error.message : "Unable to load game forecasts.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [reload]);

  useEffect(() => () => predictionController.current?.abort(), []);

  function cancelPrediction() {
    predictionController.current?.abort();
    setPredicting(false);
    setPredictionError(null);
  }

  function changeMatchup() {
    cancelPrediction();
    setResult(null);
    setSelectedGameId(null);
  }

  function selectGame(game: UpcomingGame) {
    if (!schedule) return;
    cancelPrediction();
    setSelectedGameId(game.game_id);
    setHomeTeam(game.home_team);
    setAwayTeam(game.away_team);
    setNeutral(game.neutral);
    setResult({ ...schedule, forecast: game.forecast });
  }

  async function predict(matchup: MatchupRequest) {
    predictionController.current?.abort();
    const controller = new AbortController();
    predictionController.current = controller;
    lastRequest.current = matchup;
    setPredictionError(null);
    setPredicting(true);
    setSelectedGameId(null);
    setResult(null);
    try {
      const query = new URLSearchParams({ ...matchup, neutral: String(matchup.neutral) });
      const data = await fetchData<ForecastResponse>(`${API_BASE}/api/forecast?${query}`, controller.signal);
      if (!controller.signal.aborted) setResult(data);
    } catch (error) {
      if (!controller.signal.aborted) {
        setPredictionError(error instanceof Error ? error.message : "Unable to generate this forecast.");
      }
    } finally {
      if (!controller.signal.aborted) setPredicting(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (homeTeam && awayTeam && homeTeam !== awayTeam) {
      void predict({ home_team: homeTeam, away_team: awayTeam, neutral });
    }
  }

  const selectedGame = schedule?.games.find((game) => game.game_id === selectedGameId);
  const activeModel = result?.model ?? schedule?.model;

  return (
    <main className="page forecast-page">
      <Link className="forecast-back" to="/">← NFL Analytics</Link>
      <header className="forecast-hero">
        <div>
          <p className="eyebrow">THE NEXT KICKOFF</p>
          <h1>Game <span>forecasts.</span></h1>
          <p className="subtitle">Look ahead. Pick a matchup to explore projected scores, win chances, and the room for an upset.</p>
        </div>
        <div className="forecast-model-stamp">
          <span className="forecast-experimental">Experimental model</span>
          {activeModel && <small>Results through {dateLabel(activeModel.trained_through)}</small>}
        </div>
      </header>

      {loading && <div className="forecast-status" role="status"><span className="forecast-loading-dot" /> Loading the next matchups and team forecasts…</div>}

      {loadError && <div className="forecast-status forecast-error" role="alert"><p>{loadError}</p><button className="forecast-button" onClick={() => { setLoading(true); setLoadError(null); setReload((value) => value + 1); }}>Try again</button></div>}

      {schedule && !loading && !loadError && <>
        <section className="forecast-upcoming" aria-labelledby="forecast-upcoming-title">
          <div className="forecast-section-heading">
            <h2 id="forecast-upcoming-title">On the schedule</h2>
            <span>{schedule.games.length} upcoming {schedule.games.length === 1 ? "game" : "games"}</span>
          </div>
          {schedule.games.length > 0 ? <div className="forecast-game-list">
            {schedule.games.map((game) => <button
              key={game.game_id}
              className={`forecast-game-choice${game.game_id === selectedGameId ? " is-selected" : ""}`}
              aria-pressed={game.game_id === selectedGameId}
              onClick={() => selectGame(game)}
            >
              <span>WEEK {game.week} <span>{dateLabel(game.date)}</span></span>
              <strong>{game.away_team} <small>{game.neutral ? "vs" : "@"}</small> {game.home_team}</strong>
              <span>{game.forecast.favorite ? `${game.forecast.favorite} ${percent(Math.max(game.forecast.home_win_probability, game.forecast.away_win_probability))}` : "Even matchup"}<span aria-hidden="true">↗</span></span>
            </button>)}
          </div> : <p className="forecast-empty-schedule">No upcoming games are available in the current schedule. Create your own matchup below.</p>}
        </section>

        <section className="forecast-builder" aria-labelledby="forecast-builder-title">
          <div className="forecast-builder-heading">
            <p className="eyebrow">WHAT IF?</p>
            <h2 id="forecast-builder-title">Build a matchup</h2>
            <p>Any two teams. Your home field.</p>
          </div>
          <form className="forecast-form" onSubmit={submit}>
            <div className="forecast-team-inputs">
              <label htmlFor="forecast-away">{neutral ? "Team 1" : "Away team"}
                <select id="forecast-away" value={awayTeam} onChange={(event) => { changeMatchup(); setAwayTeam(event.target.value); }} disabled={schedule.teams.length < 2} required>
                  {schedule.teams.map((team) => <option key={team} value={team}>{team}</option>)}
                </select>
              </label>
              <span className="forecast-form-versus" aria-hidden="true">{neutral ? "VS" : "@"}</span>
              <label htmlFor="forecast-home">{neutral ? "Team 2" : "Home team"}
                <select id="forecast-home" value={homeTeam} onChange={(event) => { changeMatchup(); setHomeTeam(event.target.value); }} disabled={schedule.teams.length < 2} required>
                  {schedule.teams.map((team) => <option key={team} value={team}>{team}</option>)}
                </select>
              </label>
            </div>
            <div className="forecast-form-actions">
              <label className="forecast-neutral"><input type="checkbox" checked={neutral} onChange={(event) => { changeMatchup(); setNeutral(event.target.checked); }} /> Neutral field</label>
              <button className="forecast-button" type="submit" disabled={predicting || !homeTeam || !awayTeam || homeTeam === awayTeam}>{predicting ? "Predicting…" : "Predict matchup →"}</button>
            </div>
            {homeTeam && homeTeam === awayTeam && <p className="forecast-form-hint" role="status">Choose two different teams to make a forecast.</p>}
            {schedule.teams.length < 2 && <p className="forecast-form-hint">More team history is needed before creating matchups.</p>}
          </form>
        </section>

        <div className="forecast-result-region" aria-live="polite" aria-busy={predicting}>
          {predicting && <div className="forecast-status" role="status"><span className="forecast-loading-dot" /> Projecting {awayTeam} against {homeTeam}…</div>}
          {predictionError && <div className="forecast-status forecast-error" role="alert"><p>{predictionError}</p><button className="forecast-button" onClick={() => { if (lastRequest.current) void predict(lastRequest.current); }}>Retry forecast</button></div>}
          {result && <Scoreboard result={result} game={selectedGame} />}
          {!result && !predicting && !predictionError && <div className="forecast-status forecast-ready"><span aria-hidden="true">↗</span><h2>Your next game starts here.</h2><p>Choose two teams and predict the matchup.</p></div>}
        </div>

        {activeModel && <ModelDetails model={activeModel} cutoff={result?.data_cutoff ?? schedule.data_cutoff} />}
      </>}
    </main>
  );
}
