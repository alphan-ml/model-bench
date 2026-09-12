/**
 * Pure data/insight logic for web/index.html (the Model Bench page,
 * SPEC-model-bench.md §7.1). Everything here is DOM-free and testable
 * directly; the only DOM-touching code is render() at the bottom, which
 * mounts these results onto the page's actual elements.
 *
 * Input shape is one `results.json` "models" entry as report.py writes it
 * (SPEC-model-bench.md §6.3): { key, model_id, adapter, n_rows, n_errors,
 * accuracy_fine, accuracy_coarse, cost_per_1k_usd, latency_p50_ms,
 * latency_p95_ms, brier, reliability, worst_intents_fine, worst_groups_coarse }.
 */
import { renderBarChartSvg, renderReliabilityChartSvg, assignModelColors, escapeXml } from './charts.js';

/** §7.1 item 2: "Sorted by accuracy (fine) descending." */
export function sortedLeaderboard(models) {
  return [...models].sort((a, b) => b.accuracy_fine - a.accuracy_fine);
}

export function formatPercent(fraction, decimals = 1) {
  return `${(Number(fraction) * 100).toFixed(decimals)}%`;
}

export function formatUsdPer1k(usd, decimals = 4) {
  return `$${Number(usd).toFixed(decimals)}`;
}

export function formatSeconds(ms, decimals = 2) {
  return `${(Number(ms) / 1000).toFixed(decimals)}s`;
}

export function formatBrier(brier, decimals = 3) {
  return Number(brier).toFixed(decimals);
}

/**
 * The four headline facts §7.1 item 1 asks for: best accuracy, cheapest,
 * best calibrated, and the accuracy-vs-cost gap. Pure data, no HTML — see
 * insightBulletsHtml() for the rendered <strong>-wrapped bullet text.
 */
export function computeHeadlineInsights(models) {
  if (!models || models.length === 0) return null;

  const byAccuracyDesc = sortedLeaderboard(models);
  const bestAccuracy = byAccuracyDesc[0];

  const cheapest = [...models].sort((a, b) => a.cost_per_1k_usd - b.cost_per_1k_usd)[0];
  const priciest = [...models].sort((a, b) => b.cost_per_1k_usd - a.cost_per_1k_usd)[0];

  // Lower Brier is better calibrated (SPEC §6.2).
  const bestCalibrated = [...models].sort((a, b) => a.brier - b.brier)[0];

  const accuracyGapPp = (bestAccuracy.accuracy_fine - cheapest.accuracy_fine) * 100;
  const costGapUsd = bestAccuracy.cost_per_1k_usd - cheapest.cost_per_1k_usd;

  return {
    bestAccuracy,
    cheapest,
    priciest,
    bestCalibrated,
    sameModelIsBestAndCheapest: bestAccuracy.key === cheapest.key,
    accuracyGapPp,
    costGapUsd,
  };
}

/** Renders computeHeadlineInsights()'s output as bullet HTML strings, each
 * "what and so what" with the numbers in <strong> — per §7.1 item 1. Callers
 * insert these with innerHTML (not textContent), same as the rest of this
 * page's insight card. */
export function insightBulletsHtml(insights) {
  if (!insights) return ['No results yet.'];
  const { bestAccuracy, cheapest, bestCalibrated, sameModelIsBestAndCheapest, accuracyGapPp, costGapUsd } = insights;

  const bullets = [];
  bullets.push(
    `<strong>${escapeXml(bestAccuracy.key)}</strong> is the most accurate model at ` +
    `<strong>${formatPercent(bestAccuracy.accuracy_fine)}</strong> fine-grained intent accuracy — ` +
    `that is the model to pick when getting the routing right matters more than saving money.`
  );
  bullets.push(
    `<strong>${escapeXml(cheapest.key)}</strong> is the cheapest at ` +
    `<strong>${formatUsdPer1k(cheapest.cost_per_1k_usd)}</strong> per 1,000 messages — ` +
    `that is the model to pick for high-volume traffic where cost dominates.`
  );
  bullets.push(
    `<strong>${escapeXml(bestCalibrated.key)}</strong> is the best calibrated model ` +
    `(Brier score <strong>${formatBrier(bestCalibrated.brier)}</strong>, lower is better) — ` +
    `its stated confidence can be trusted as a real probability more than the others'.`
  );
  if (sameModelIsBestAndCheapest) {
    bullets.push(
      `<strong>${escapeXml(bestAccuracy.key)}</strong> is both the most accurate and the cheapest here — ` +
      `there is no accuracy-vs-cost tradeoff to make among these 5 models.`
    );
  } else {
    bullets.push(
      `Paying more does not always buy more accuracy: <strong>${escapeXml(bestAccuracy.key)}</strong> costs ` +
      `<strong>${formatUsdPer1k(costGapUsd)}</strong> more per 1,000 messages than ` +
      `<strong>${escapeXml(cheapest.key)}</strong>, for <strong>${accuracyGapPp.toFixed(1)} points</strong> ` +
      `more fine-grained accuracy — whether that trade is worth it depends on how costly a wrong routing is.`
    );
  }
  return bullets;
}

/** One of the 4 headline bar charts (§7.1 item 3). `metricKey` picks the
 * field; `colorByKey` (from assignModelColors) keeps each model's color
 * constant across every chart on the page (rule 11). Sorted the same way
 * as the leaderboard (best first) so a reader can visually match bars to
 * table rows in order. */
export function metricBars(models, metricKey, colorByKey, { sortDescending = true } = {}) {
  const sorted = [...models].sort((a, b) => (sortDescending ? b[metricKey] - a[metricKey] : a[metricKey] - b[metricKey]));
  return sorted.map((m) => ({ label: m.key, value: m[metricKey], color: colorByKey[m.key] }));
}

/**
 * The 4 headline metric charts this page shows, per §7.1 item 3 ("Four bar
 * charts... one per metric"). The spec names 6 leaderboard columns
 * (accuracy fine/coarse, cost, p50/p95 latency, Brier) but says exactly 4
 * charts — DISCLOSED CHOICE (documented as D18 in CONTEXT.md, same pattern
 * as D15/D16): the 4 charted here are fine-grained accuracy, cost per 1k,
 * p50 latency, and Brier — one per dimension (quality / price / speed /
 * calibration), with coarse accuracy and p95 latency staying visible in
 * the leaderboard table and the reliability chart covering calibration in
 * more depth than a single Brier bar can. Flagged for Leon in the W-A3
 * report in case a different 4 (or all 6) was intended.
 */
export function headlineChartSpecs(models) {
  const colorByKey = assignModelColors(models.map((m) => m.key));
  return [
    {
      title: 'Accuracy (fine-grained intent)', xLabel: 'Model', yLabel: 'Accuracy',
      bars: metricBars(models, 'accuracy_fine', colorByKey),
      formatValue: (n) => formatPercent(n, 0),
    },
    {
      title: 'Cost per 1,000 messages', xLabel: 'Model', yLabel: 'Cost (USD)',
      bars: metricBars(models, 'cost_per_1k_usd', colorByKey, { sortDescending: false }),
      formatValue: (n) => formatUsdPer1k(n),
    },
    {
      title: 'p50 latency', xLabel: 'Model', yLabel: 'Latency (s)',
      bars: metricBars(models, 'latency_p50_ms', colorByKey, { sortDescending: false }),
      formatValue: (n) => formatSeconds(n),
    },
    {
      title: 'Calibration (Brier score, lower is better)', xLabel: 'Model', yLabel: 'Brier score',
      bars: metricBars(models, 'brier', colorByKey, { sortDescending: false }),
      formatValue: (n) => formatBrier(n),
    },
  ];
}

/** Renders all 4 headline charts to SVG strings, keyed by chart title, for
 * the caller to drop into the page's chart containers. */
export function renderHeadlineChartsSvg(models) {
  return headlineChartSpecs(models).map((spec) => renderBarChartSvg(spec));
}

/**
 * The one calibration chart (§7.1 item 4): stated confidence vs observed
 * accuracy, all 5 models on one plot, dashed y=x diagonal. reliability
 * bins store mean_confidence on a 0-100 scale (metrics.py's
 * reliability_bins) and observed_accuracy already as a 0-1 fraction;
 * renderReliabilityChartSvg expects both axes in [0,1], so confidence is
 * normalized here, once, in the one place that knows both scales.
 */
export function reliabilitySeries(models) {
  const colorByKey = assignModelColors(models.map((m) => m.key));
  return models.map((m) => ({
    key: m.key,
    color: colorByKey[m.key],
    points: (m.reliability ?? [])
      .filter((bin) => bin.n > 0)
      .map((bin) => ({ x: bin.mean_confidence / 100, y: bin.observed_accuracy })),
  }));
}

export function renderReliabilityChart(models) {
  return renderReliabilityChartSvg({
    title: 'Calibration: stated confidence vs. observed accuracy',
    xLabel: 'Stated confidence', yLabel: 'Observed accuracy',
    series: reliabilitySeries(models),
  });
}

/** §7.1 item 5: "Where the cheap model fails" — worst 10 intents per model
 * at the fine level. worst_intents_fine already arrives sorted worst-first
 * (metrics.per_intent), so this is a slice, not a re-sort — kept as its
 * own named function so the "10" is one obvious, greppable constant. */
export function worstIntentsTable(model, topN = 10) {
  return (model.worst_intents_fine ?? []).slice(0, topN);
}

/** §7.1 item 7's methodology section needs n=3,080, prices-as-of, and the
 * live-box cost counter — this pulls the header facts out of the results
 * object itself so the page never hard-codes them. */
export function methodologyFacts(results) {
  return {
    nRows: results.n_rows_expected,
    pricesAsOf: results.prices_as_of,
    generatedAt: results.generated_at,
  };
}

/**
 * Mounts the whole page from a results object (already inlined into
 * window.__RESULTS__ by scripts_build_web_page.py — see that script's
 * docstring for why this page has no runtime fetch for its tables/charts).
 * The only DOM-touching function in this module.
 */
export function render(results, doc = document) {
  const models = results.models ?? [];
  const leaderboard = sortedLeaderboard(models);
  const insights = computeHeadlineInsights(models);

  doc.getElementById('insights-list').innerHTML = insightBulletsHtml(insights).map((b) => `<li>${b}</li>`).join('');

  const tbody = doc.getElementById('leaderboard-body');
  tbody.innerHTML = leaderboard.map((m) => `
    <tr>
      <td>${escapeXml(m.key)}</td>
      <td>${formatPercent(m.accuracy_fine)}</td>
      <td>${formatPercent(m.accuracy_coarse)}</td>
      <td>${formatUsdPer1k(m.cost_per_1k_usd)}</td>
      <td>${formatSeconds(m.latency_p50_ms)}</td>
      <td>${formatSeconds(m.latency_p95_ms)}</td>
      <td>${formatBrier(m.brier)}</td>
    </tr>`).join('');

  const chartContainerIds = ['chart-accuracy', 'chart-cost', 'chart-latency', 'chart-brier'];
  renderHeadlineChartsSvg(models).forEach((svg, i) => {
    doc.getElementById(chartContainerIds[i]).innerHTML = svg;
  });

  doc.getElementById('chart-calibration').innerHTML = renderReliabilityChart(models);

  const reliabilityTablesEl = doc.getElementById('reliability-tables');
  reliabilityTablesEl.innerHTML = models.map((m) => `
    <div class="reliability-model">
      <h3>${escapeXml(m.key)}</h3>
      <table>
        <thead><tr><th>Confidence bin</th><th>n</th><th>Mean confidence</th><th>Observed accuracy</th></tr></thead>
        <tbody>${(m.reliability ?? []).map((b) => `
          <tr><td>${b.bin}</td><td>${b.n}</td><td>${b.mean_confidence.toFixed(1)}</td><td>${formatPercent(b.observed_accuracy)}</td></tr>
        `).join('')}</tbody>
      </table>
    </div>`).join('');

  const worstEl = doc.getElementById('worst-intents');
  worstEl.innerHTML = models.map((m) => `
    <div class="worst-model">
      <h3>${escapeXml(m.key)}</h3>
      <table>
        <thead><tr><th>Intent</th><th>n</th><th>Accuracy</th></tr></thead>
        <tbody>${worstIntentsTable(m).map((row) => `
          <tr><td>${escapeXml(row.name)}</td><td>${row.n}</td><td>${formatPercent(row.accuracy)}</td></tr>
        `).join('')}</tbody>
      </table>
    </div>`).join('');

  const facts = methodologyFacts(results);
  doc.getElementById('methodology-n-rows').textContent = String(facts.nRows);
  doc.getElementById('methodology-prices-as-of').textContent = facts.pricesAsOf ?? 'unknown';
  doc.getElementById('methodology-generated-at').textContent = facts.generatedAt ?? 'unknown';
}
