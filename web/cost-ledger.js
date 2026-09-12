/**
 * Client logic for cost-ledger.html. Pure/DOM-light functions are exported
 * and unit-tested directly; the render() function at the bottom is the
 * only part that touches document, and is exercised visually via
 * web/dev-server.js in a real browser (see tests/cost-ledger.test.js's
 * header comment for why that split exists).
 */
import { renderBarChartSvg, formatMonD } from './charts.js';

/**
 * Builds the "Overall insights" bullet card's four facts from a set of
 * /api/meter/ledger responses (one per grouping) plus /api/meter/health.
 * Pure function — no fetch, no DOM — so it's directly testable.
 *
 * @param {{
 *   health: { est_month_to_date_cost_usd: number, prices_as_of: string|null },
 *   byUseCase: { rows: { key: string, cost_usd: number, calls: number }[] },
 *   byStep: { rows: { key: string, cost_usd: number, calls: number }[] },
 * }} data
 */
export function computeInsights(data) {
  const { health, byUseCase, byStep } = data;

  const stepsWithCostPerAnswer = byStep.rows
    .filter((r) => r.calls > 0)
    .map((r) => ({ key: r.key, costPerAnswer: r.cost_usd / r.calls }));

  let cheapest = null;
  let dearest = null;
  for (const s of stepsWithCostPerAnswer) {
    if (!cheapest || s.costPerAnswer < cheapest.costPerAnswer) cheapest = s;
    if (!dearest || s.costPerAnswer > dearest.costPerAnswer) dearest = s;
  }

  const totalUseCaseCost = byUseCase.rows.reduce((sum, r) => sum + r.cost_usd, 0);
  const shareByUseCase = byUseCase.rows.map((r) => ({
    key: r.key,
    share: totalUseCaseCost > 0 ? r.cost_usd / totalUseCaseCost : 0,
  }));

  return {
    monthToDateCostUsd: health.est_month_to_date_cost_usd,
    pricesAsOf: health.prices_as_of,
    cheapestStep: cheapest,
    dearestStep: dearest,
    shareByUseCase,
  };
}

/** Formats a 0..1 fraction as a percentage string, e.g. 0.6183 -> "62%". */
export function formatPercent(fraction) {
  return `${Math.round((Number(fraction) || 0) * 100)}%`;
}

/** Builds the insight bullets (plain strings; the page wraps each in <li>). */
export function insightBullets(insights) {
  const bullets = [];
  bullets.push(`Month-to-date cost: $${(insights.monthToDateCostUsd ?? 0).toFixed(4)}.`);
  if (insights.cheapestStep) {
    bullets.push(`Cheapest step per answer: ${insights.cheapestStep.key} ($${insights.cheapestStep.costPerAnswer.toFixed(6)}/answer).`);
  }
  if (insights.dearestStep) {
    bullets.push(`Dearest step per answer: ${insights.dearestStep.key} ($${insights.dearestStep.costPerAnswer.toFixed(6)}/answer).`);
  }
  if (insights.shareByUseCase.length > 0) {
    const shares = insights.shareByUseCase
      .map((s) => `${s.key} ${formatPercent(s.share)}`)
      .join(', ');
    bullets.push(`Share of cost by use case: ${shares}.`);
  }
  return bullets;
}

/** Turns a day-grouped ledger response into bar-chart input, one bar per
 * day, oldest first. Labels use "Mon D" (see charts.js's formatMonD doc
 * comment for why, not the spec-literal "Mon YY" — D16). */
export function dayRowsToBars(byDay) {
  return [...byDay.rows]
    .sort((a, b) => (a.key < b.key ? -1 : 1))
    .map((r) => ({ label: formatMonD(r.key), value: r.cost_usd }));
}

/** Turns a use_case/model-grouped ledger response into bar-chart input. */
export function keyRowsToBars(rows) {
  return rows.map((r) => ({ label: r.key, value: r.cost_usd }));
}

/** Cost per answer by step = cost_usd / calls for each step row. */
export function stepRowsToCostPerAnswerBars(rows) {
  return rows
    .filter((r) => r.calls > 0)
    .map((r) => ({ label: r.key, value: r.cost_usd / r.calls }));
}

async function fetchJson(url, fetchImpl) {
  const res = await fetchImpl(url);
  if (!res.ok) throw new Error(`${url} failed: ${res.status}`);
  return res.json();
}

/** Fetches everything the page needs in parallel. Exported so a test can
 * verify the exact set of endpoints it calls, without touching the DOM. */
export async function loadLedgerData(fetchImpl = fetch) {
  const [health, byDay, byUseCase, byModel, byStep] = await Promise.all([
    fetchJson('/api/meter/health', fetchImpl),
    fetchJson('/api/meter/ledger?window=30d&group=day', fetchImpl),
    fetchJson('/api/meter/ledger?window=30d&group=use_case', fetchImpl),
    fetchJson('/api/meter/ledger?window=30d&group=model', fetchImpl),
    fetchJson('/api/meter/ledger?window=30d&group=step', fetchImpl),
  ]);
  return { health, byDay, byUseCase, byModel, byStep };
}

/** Mounts the full page from live data. The only DOM-touching function
 * in this file. */
export async function render(fetchImpl = fetch) {
  const data = await loadLedgerData(fetchImpl);
  const insights = computeInsights(data);

  document.getElementById('insights-list').innerHTML = insightBullets(insights)
    .map((b) => `<li>${b}</li>`).join('');

  document.getElementById('explainer').textContent =
    `Every model call is priced from a dated price sheet at the moment it happens. ` +
    `Prices as of ${insights.pricesAsOf ?? 'unknown'}. This page shows the true cost of running these demos.`;

  document.getElementById('chart-by-day').innerHTML = renderBarChartSvg({
    title: 'Cost per day', xLabel: 'Day', yLabel: 'Cost (USD)',
    bars: dayRowsToBars(data.byDay), formatValue: (n) => `$${n.toFixed(4)}`,
  });
  document.getElementById('chart-by-use-case').innerHTML = renderBarChartSvg({
    title: 'Cost by use case', xLabel: 'Use case', yLabel: 'Cost (USD)',
    bars: keyRowsToBars(data.byUseCase.rows), formatValue: (n) => `$${n.toFixed(4)}`,
  });
  document.getElementById('chart-by-model').innerHTML = renderBarChartSvg({
    title: 'Cost by model', xLabel: 'Model', yLabel: 'Cost (USD)',
    bars: keyRowsToBars(data.byModel.rows), formatValue: (n) => `$${n.toFixed(4)}`,
  });
  document.getElementById('chart-cost-per-answer').innerHTML = renderBarChartSvg({
    title: 'Cost per answer by step', xLabel: 'Step', yLabel: 'Cost per answer (USD)',
    bars: stepRowsToCostPerAnswerBars(data.byStep.rows), formatValue: (n) => `$${n.toFixed(4)}`,
  });

  const tbody = document.getElementById('ledger-table-body');
  tbody.innerHTML = [...data.byDay.rows].sort((a, b) => (a.key < b.key ? -1 : 1)).map((r) => `
    <tr>
      <td>${formatMonD(r.key)}</td>
      <td>${r.calls}</td>
      <td>$${r.cost_usd.toFixed(4)}</td>
      <td>${r.p50_latency_ms} ms</td>
    </tr>`).join('');
}
