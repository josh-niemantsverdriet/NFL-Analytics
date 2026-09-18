import test from 'node:test';
import assert from 'node:assert/strict';
import { rankTeams } from '../src/rankings.ts';

test('ties use SQL competition ranks, with missing metrics last', () => {
  const teams = [
    { team: 'BUF', epa_per_play: 0.2, def_epa_per_play: -0.1 },
    { team: 'KC', epa_per_play: 0.2, def_epa_per_play: -0.1 },
    { team: 'MIA', epa_per_play: 0.1, def_epa_per_play: 0.0 },
    { team: 'NYJ', epa_per_play: null, def_epa_per_play: null },
  ];
  const original = structuredClone(teams);
  const ranked = rankTeams(teams);
  assert.deepEqual(ranked.map(t => t.offense_rank), [1, 1, 3, 4]);
  assert.deepEqual(ranked.map(t => t.defense_rank), [1, 1, 3, 4]);
  assert.deepEqual(ranked.map(t => t.overall_rank), [1, 1, 3, 4]);
  assert.deepEqual(rankTeams([...teams].reverse()), ranked);
  assert.deepEqual(teams, original);
});

test('3,200 simulated teams agree with pairwise rank definitions', () => {
  for (let seed = 0; seed < 100; seed++) {
    const teams = Array.from({ length: 32 }, (_, index) => ({
      team: `T${index}`, epa_per_play: (index * 7 + seed * 13) % 9 - 4,
      def_epa_per_play: (index * 11 + seed * 3) % 7 - 3,
    }));
    const ranked = rankTeams(teams);
    for (const team of ranked) {
      assert.equal(team.offense_rank, 1 + teams.filter(other => other.epa_per_play > team.epa_per_play).length);
      assert.equal(team.defense_rank, 1 + teams.filter(other => other.def_epa_per_play < team.def_epa_per_play).length);
      assert.equal(team.overall_rank, 1 + ranked.filter(other => other.overall_score < team.overall_score).length);
    }
  }
});
