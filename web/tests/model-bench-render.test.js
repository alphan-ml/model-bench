import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import {
  sortedLeaderboard, computeHeadlineInsights, insightBulletsHtml,
  metricBars, headlineChartSpecs, reliabilitySeries, renderReliabilityChart,
  worstIntentsTable, methodologyFacts,
  formatPercent, formatUsdPer1k, formatSeconds, formatBrier,
} from '../model-bench-render.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(__dirname, '..', '..');
const SAMPLE = JSON.parse(readFileSync(path.join(REPO_ROOT, 'results.sample.json'), 'utf8'));
const MODELS = SAMPLE.models;

describe('formatting helpers', () => {
  test('formatPercent', () => {
    assert.equal(formatPercent(0.913), '91.3%');
    assert.equal(formatPercent(0.913, 0), '91%');
  });
  test('formatUsdPer1k', () => {
    assert.equal(formatUsdPer1k(0.11), '$0.1100');
  });
  test('formatSeconds', () => {
    assert.equal(formatSeconds(640), '0.64s');
  });
  test('formatBrier', () => {
    assert.equal(formatBrier(0.0951234), '0.095');
  });
});

describe('sortedLeaderboard', () => {
  test('sorts by accuracy_fine descending', () => {
    const sorted = sortedLeaderboard(MODELS);
    for (let i = 1; i < sorted.length; i++) {
      assert.ok(sorted[i - 1].accuracy_fine >= sorted[i].accuracy_fine);
    }
  });

  test('does not mutate the input array', () => {
    const copy = [...MODELS];
    sortedLeaderboard(MODELS);
    assert.deepEqual(MODELS, copy);
  });
});

describe('computeHeadlineInsights', () => {
  const insights = computeHeadlineInsights(MODELS);

  test('picks the highest-accuracy model as bestAccuracy', () => {
    const expected = [...MODELS].sort((a, b) => b.accuracy_fine - a.accuracy_fine)[0];
    assert.equal(insights.bestAccuracy.key, expected.key);
  });

  test('picks the lowest-cost model as cheapest', () => {
    const expected = [...MODELS].sort((a, b) => a.cost_per_1k_usd - b.cost_per_1k_usd)[0];
    assert.equal(insights.cheapest.key, expected.key);
  });

  test('picks the lowest-brier model as bestCalibrated (lower Brier is better)', () => {
    const expected = [...MODELS].sort((a, b) => a.brier - b.brier)[0];
    assert.equal(insights.bestCalibrated.key, expected.key);
  });

  test('flags when the same model is both most accurate and cheapest', () => {
    const oneModel = [MODELS[0]];
    const single = computeHeadlineInsights(oneModel);
    assert.equal(single.sameModelIsBestAndCheapest, true);
    // The sample fixture is built so the best-accuracy model is NOT the
    // cheapest one (see scripts_build_results_sample.py's header comment).
    assert.equal(insights.sameModelIsBestAndCheapest, false);
  });

  test('returns null for an empty model list rather than throwing', () => {
    assert.equal(computeHeadlineInsights([]), null);
  });
});

describe('insightBulletsHtml', () => {
  const bullets = insightBulletsHtml(computeHeadlineInsights(MODELS));

  test('returns exactly 4 bullets (best accuracy, cheapest, best calibrated, the gap)', () => {
    assert.equal(bullets.length, 4);
  });

  test('every bullet wraps its numbers in <strong> (spec: "numbers bold")', () => {
    for (const b of bullets) {
      assert.match(b, /<strong>/, `bullet has no <strong>: ${b}`);
    }
  });

  test('handles a null insights object without throwing', () => {
    assert.doesNotThrow(() => insightBulletsHtml(null));
  });
});

describe('metricBars / headlineChartSpecs', () => {
  test('metricBars sorts descending by default and colors every bar', () => {
    const colorByKey = { a: '#111', b: '#222' };
    const bars = metricBars([{ key: 'a', x: 1 }, { key: 'b', x: 2 }], 'x', colorByKey);
    assert.equal(bars[0].label, 'b');
    assert.equal(bars[0].color, '#222');
  });

  test('headlineChartSpecs returns exactly 4 chart specs', () => {
    assert.equal(headlineChartSpecs(MODELS).length, 4);
  });

  test('every model gets the SAME color across all 4 chart specs (identity color, rule 11)', () => {
    const specs = headlineChartSpecs(MODELS);
    const colorForKey = {};
    for (const spec of specs) {
      for (const bar of spec.bars) {
        if (colorForKey[bar.label] === undefined) {
          colorForKey[bar.label] = bar.color;
        } else {
          assert.equal(bar.color, colorForKey[bar.label], `${bar.label} changed color between charts`);
        }
      }
    }
  });

  test('cost and latency charts sort cheapest/fastest first', () => {
    const [, costSpec, latencySpec] = headlineChartSpecs(MODELS);
    for (let i = 1; i < costSpec.bars.length; i++) {
      assert.ok(costSpec.bars[i - 1].value <= costSpec.bars[i].value);
    }
    for (let i = 1; i < latencySpec.bars.length; i++) {
      assert.ok(latencySpec.bars[i - 1].value <= latencySpec.bars[i].value);
    }
  });
});

describe('reliabilitySeries / renderReliabilityChart', () => {
  test('one series per model, points normalized to [0,1] on both axes', () => {
    const series = reliabilitySeries(MODELS);
    assert.equal(series.length, MODELS.length);
    for (const s of series) {
      for (const p of s.points) {
        assert.ok(p.x >= 0 && p.x <= 1, `x=${p.x} out of [0,1]`);
        assert.ok(p.y >= 0 && p.y <= 1, `y=${p.y} out of [0,1]`);
      }
    }
  });

  test('excludes empty bins (n === 0)', () => {
    const withEmptyBin = [{
      key: 'test-model', reliability: [
        { bin: '0-10', n: 0, mean_confidence: 0, observed_accuracy: 0 },
        { bin: '10-20', n: 5, mean_confidence: 15, observed_accuracy: 0.4 },
      ],
    }];
    const series = reliabilitySeries(withEmptyBin);
    assert.equal(series[0].points.length, 1);
  });

  test('renderReliabilityChart produces a real <svg> string', () => {
    assert.match(renderReliabilityChart(MODELS), /^\s*<svg/);
  });
});

describe('worstIntentsTable', () => {
  test('returns the first 10 entries of the already-worst-first list', () => {
    const table = worstIntentsTable(MODELS[0]);
    assert.equal(table.length, 10);
    assert.deepEqual(table, MODELS[0].worst_intents_fine.slice(0, 10));
  });

  test('is sorted worst (lowest accuracy) first', () => {
    const table = worstIntentsTable(MODELS[0]);
    for (let i = 1; i < table.length; i++) {
      assert.ok(table[i - 1].accuracy <= table[i].accuracy);
    }
  });
});

describe('methodologyFacts', () => {
  test('pulls n_rows_expected, prices_as_of, generated_at straight from the results object', () => {
    const facts = methodologyFacts(SAMPLE);
    assert.equal(facts.nRows, SAMPLE.n_rows_expected);
    assert.equal(facts.pricesAsOf, SAMPLE.prices_as_of);
    assert.equal(facts.generatedAt, SAMPLE.generated_at);
  });
});
