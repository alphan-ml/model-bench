import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  renderBarChartSvg, renderReliabilityChartSvg, assignModelColors,
  formatMonYy, formatMonD, fitLabel, escapeXml,
} from '../charts.js';

describe('renderBarChartSvg', () => {
  const basic = () => renderBarChartSvg({
    title: 'Cost per day',
    xLabel: 'Day',
    yLabel: 'Cost (USD)',
    bars: [{ label: 'Sep 10', value: 1.5 }, { label: 'Sep 11', value: 3.2 }],
  });

  test('includes the title, axis titles, and an <svg> root', () => {
    const svg = basic();
    assert.match(svg, /^\s*<svg/);
    assert.match(svg, />Cost per day</);
    assert.match(svg, />Day</);
    assert.match(svg, />Cost \(USD\)</);
  });

  test('draws two axis lines (x and y) and no gridlines', () => {
    const svg = basic();
    const lineCount = (svg.match(/<line /g) ?? []).length;
    assert.equal(lineCount, 2, 'exactly the x-axis and y-axis lines, no gridlines');
  });

  test('draws one <rect> bar per data point', () => {
    const svg = basic();
    const rectCount = (svg.match(/<rect /g) ?? []).length;
    assert.equal(rectCount, 2);
  });

  test('draws a value label for every bar (labels inside bars, not tooltips)', () => {
    const svg = basic();
    assert.match(svg, />1\.50</);
    assert.match(svg, />3\.20</);
  });

  test('draws tick value text on the y axis', () => {
    const svg = renderBarChartSvg({
      title: 't', xLabel: 'x', yLabel: 'y',
      bars: [{ label: 'a', value: 10 }],
      formatValue: (n) => String(Math.round(n)),
    });
    // 4 interior ticks + 1 at zero = 5 tick labels, plus one bar-top label.
    assert.match(svg, />0</);
  });

  test('escapes a title containing markup-sensitive characters', () => {
    const svg = renderBarChartSvg({
      title: 'A & B <script>', xLabel: 'x', yLabel: 'y', bars: [],
    });
    assert.doesNotMatch(svg, /<script>/);
    assert.match(svg, /A &amp; B &lt;script&gt;/);
  });

  test('handles an empty bars array without throwing (all-zero window)', () => {
    assert.doesNotThrow(() => renderBarChartSvg({ title: 't', xLabel: 'x', yLabel: 'y', bars: [] }));
  });

  test('a tall bar\'s value label is white-on-blue and stays inside the plot area, not on the axis line', () => {
    // Regression test for a real bug caught by visual (Playwright)
    // verification: the label-Y clamp used Math.max where it needed
    // Math.min, so a short bar's label could slide PAST the x-axis and
    // overlap the category-label text below it.
    const svg = renderBarChartSvg({
      title: 't', xLabel: 'x', yLabel: 'y', height: 340,
      bars: [{ label: 'big', value: 100 }],
    });
    const labelYs = [...svg.matchAll(/<text x="[\d.]+" y="([\d.]+)" text-anchor="middle" fill="#ffffff"/g)]
      .map((m) => Number(m[1]));
    assert.equal(labelYs.length, 1);
    // margin.top=44, plotH = 340-44-64=232 -> bottom of plot = 276.
    assert.ok(labelYs[0] <= 276 - 4 + 0.5, `label y=${labelYs[0]} should stay at/above the plot floor (276-4)`);
    assert.ok(labelYs[0] >= 44 + 12 - 0.5, `label y=${labelYs[0]} should stay at/below the plot ceiling (44+12)`);
  });

  test('a near-zero-height bar\'s value label falls back to dark text ABOVE the bar, not white-on-white', () => {
    // Second regression case, also caught by visual verification: a bar
    // too short to contain a legible white label used to render it half
    // on the blue bar and half on the white page background — invisible
    // where it crossed onto white. Below the inside-label height
    // threshold, the label must render in dark text instead, still
    // clamped within the plot area.
    const svg = renderBarChartSvg({
      title: 't', xLabel: 'x', yLabel: 'y', height: 340,
      bars: [{ label: 'big', value: 100 }, { label: 'tiny', value: 0.0001 }],
    });
    // font-size:11px;font-weight:600 is specific to a bar's value label
    // (the chart title and axis titles use other sizes) — this excludes
    // those from the count.
    const darkLabelYs = [...svg.matchAll(/<text x="[\d.]+" y="([\d.]+)" text-anchor="middle" fill="#111111" style="[^"]*font-size:11px;font-weight:600/g)]
      .map((m) => Number(m[1]));
    assert.equal(darkLabelYs.length, 1, 'exactly the tiny bar\'s value label should use the dark-text fallback');
    assert.ok(darkLabelYs[0] >= 44 + 12 - 0.5, 'the fallback label should still stay within the plot area, not above the title');
  });

  test('a bar with its own color overrides the default bar color (identity color per model, rule 11)', () => {
    const svg = renderBarChartSvg({
      title: 't', xLabel: 'x', yLabel: 'y',
      bars: [{ label: 'model-a', value: 1, color: '#0f9d58' }, { label: 'model-b', value: 1 }],
    });
    assert.match(svg, /<rect[^>]*fill="#0f9d58"/, 'the colored bar uses its own color');
    assert.match(svg, /<rect[^>]*fill="#1a56db"/, 'a bar with no color falls back to the chart default');
  });

  test('truncates a long category label instead of letting it overlap its neighbor', () => {
    const svg = renderBarChartSvg({
      title: 't', xLabel: 'x', yLabel: 'y',
      bars: [
        { label: 'anthropic.claude-3-5-sonnet-20240620-v1:0', value: 1 },
        { label: 'anthropic.claude-3-haiku-20240307-v1:0', value: 1 },
        { label: 'amazon.nova-lite-v1:0', value: 1 },
      ],
    });
    // The full id belongs ONLY inside the <title> tooltip, never as the
    // rendered <text> label itself (which must be short enough not to
    // overlap its neighbor).
    assert.doesNotMatch(svg, /<text[^>]*>anthropic\.claude-3-5-sonnet-20240620-v1:0<\/text>/, 'the RENDERED label should be truncated, not the full id');
    assert.match(svg, /…/, 'a truncated label ends in an ellipsis');
    assert.match(svg, /<title>anthropic\.claude-3-5-sonnet-20240620-v1:0<\/title>/, 'the full id is preserved in a tooltip');
  });
});

describe('assignModelColors', () => {
  test('gives every model key a color, stable regardless of input order', () => {
    const a = assignModelColors(['nova', 'claude-haiku', 'mistral']);
    const b = assignModelColors(['mistral', 'claude-haiku', 'nova']);
    assert.deepEqual(a, b);
    assert.equal(Object.keys(a).length, 3);
  });

  test('two different keys never collide on the same color within the palette size', () => {
    const colors = assignModelColors(['a', 'b', 'c', 'd', 'e']);
    assert.equal(new Set(Object.values(colors)).size, 5);
  });
});

describe('renderReliabilityChartSvg', () => {
  const basic = () => renderReliabilityChartSvg({
    title: 'Calibration', xLabel: 'Stated confidence', yLabel: 'Observed accuracy',
    series: [
      { key: 'claude-haiku', color: '#1a56db', points: [{ x: 0.5, y: 0.4 }, { x: 0.9, y: 0.85 }] },
      { key: 'nova', color: '#0f9d58', points: [{ x: 0.5, y: 0.6 }] },
    ],
  });

  test('includes the title and both axis titles', () => {
    const svg = basic();
    assert.match(svg, />Calibration</);
    assert.match(svg, />Stated confidence</);
    assert.match(svg, />Observed accuracy</);
  });

  test('draws exactly the x and y axis lines, no gridlines', () => {
    const svg = basic();
    // The dashed diagonal is also a <line>, so axis lines + diagonal = 3.
    const lineCount = (svg.match(/<line /g) ?? []).length;
    assert.equal(lineCount, 3, 'x-axis, y-axis, and the dashed diagonal only');
  });

  test('the diagonal reference line is dashed', () => {
    assert.match(basic(), /stroke-dasharray="4 4"/);
  });

  test('draws one point per series entry, in that series\' color', () => {
    const svg = basic();
    const blueCircles = (svg.match(/<circle[^>]*fill="#1a56db"/g) ?? []).length;
    const greenCircles = (svg.match(/<circle[^>]*fill="#0f9d58"/g) ?? []).length;
    // 2 data points + 1 legend swatch for claude-haiku; 1 data point + 1
    // legend swatch for nova.
    assert.equal(blueCircles, 3);
    assert.equal(greenCircles, 2);
  });

  test('legend lists every series by key', () => {
    const svg = basic();
    assert.match(svg, />claude-haiku</);
    assert.match(svg, />nova</);
  });

  test('handles an empty series list without throwing', () => {
    assert.doesNotThrow(() => renderReliabilityChartSvg({ title: 't', xLabel: 'x', yLabel: 'y', series: [] }));
  });

  test('handles a series with no points without throwing', () => {
    assert.doesNotThrow(() => renderReliabilityChartSvg({
      title: 't', xLabel: 'x', yLabel: 'y', series: [{ key: 'a', color: '#000', points: [] }],
    }));
  });
});

describe('fitLabel', () => {
  test('returns the label unchanged when it fits', () => {
    const { text, full } = fitLabel('area', 200, 11);
    assert.equal(text, 'area');
    assert.equal(full, 'area');
  });

  test('truncates with an ellipsis when it does not fit, and keeps the full text', () => {
    const { text, full } = fitLabel('anthropic.claude-3-5-sonnet-20240620-v1:0', 80, 11);
    assert.ok(text.length < full.length);
    assert.ok(text.endsWith('…'));
    assert.equal(full, 'anthropic.claude-3-5-sonnet-20240620-v1:0');
  });

  test('never truncates to nothing (at least 3 chars) even for a tiny width', () => {
    const { text } = fitLabel('a-very-long-model-id', 1, 11);
    assert.ok(text.length >= 3);
  });
});

describe('formatMonYy', () => {
  test('formats an ISO date as "Mon YY", per spec §1.3 — used for coarser-than-daily labels (D16)', () => {
    assert.equal(formatMonYy('2026-09-12'), 'Sep 26');
    assert.equal(formatMonYy('2026-01-01'), 'Jan 26');
    assert.equal(formatMonYy('2025-12-31'), 'Dec 25');
  });
});

describe('formatMonD', () => {
  test('formats an ISO date as "Mon D" — used for the per-day chart/table (D16)', () => {
    assert.equal(formatMonD('2026-09-12'), 'Sep 12');
    assert.equal(formatMonD('2026-01-01'), 'Jan 1');
  });

  test('three different days in the same month stay distinguishable', () => {
    const labels = ['2026-09-10', '2026-09-11', '2026-09-12'].map(formatMonD);
    assert.equal(new Set(labels).size, 3);
  });
});

describe('escapeXml', () => {
  test('escapes the five XML-sensitive characters', () => {
    assert.equal(escapeXml('<a href="x">A & B</a>'), '&lt;a href=&quot;x&quot;&gt;A &amp; B&lt;/a&gt;');
  });
});
