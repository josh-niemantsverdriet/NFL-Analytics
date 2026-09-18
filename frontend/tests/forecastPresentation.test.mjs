import test from 'node:test';
import assert from 'node:assert/strict';
import { scorePresentation } from '../src/forecastPresentation.ts';

test('central projection is distinct from the 34-10 exact mode', () => {
  const mode = { home_score: 34, away_score: 10, probability: 0.0064 };
  const central = { home_score: 26, away_score: 21, probability: 0.004, method: 'minimum_expected_absolute_error' };
  const other = { home_score: 27, away_score: 20, probability: 0.0061 };
  const scores = Object.freeze([Object.freeze(mode), Object.freeze(other)]);
  const view = scorePresentation(central, scores);
  assert.equal(view.heading, 'Typical score estimate');
  assert.equal(view.scoreKind, 'TYPICAL');
  assert.equal(view.exactProbabilityLabel, 'Probability of this exact typical score');
  assert.equal(view.alternativesHeading, 'Highest-probability exact scores');
  assert.equal(view.alternatives[0], mode);
  assert.match(view.explanation, /not the most likely exact final/);
  assert.equal(view.tiedProjection, false);
});

test('legacy modes retain their meaning and tied central projections are explicit', () => {
  const mode = { home_score: 34, away_score: 10, probability: 0.0064 };
  assert.deepEqual(scorePresentation(mode, [mode]).alternatives, []);
  assert.match(scorePresentation(mode).explanation, /most likely single result/);
  assert.equal(scorePresentation(mode).scoreKind, 'PREDICTED');
  assert.equal(scorePresentation().heading, 'Expected average score');
  assert.equal(scorePresentation({ home_score: 23, away_score: 23, probability: 0.002, method: 'minimum_expected_absolute_error' }).tiedProjection, true);
});
