/**
 * Minimal inline-SVG bar chart, shared by the cost-ledger page (and later
 * by any AREA tab that needs the same look). No charting library — the
 * BUILD INSTRUCTION's zero-dependency-by-design rule and the page-style
 * rule (rule 11) are easier to satisfy exactly with a small hand-built
 * renderer than by fighting a general-purpose library's defaults:
 *   - a title
 *   - axis lines (not just ticks floating in space)
 *   - tick values on both axes
 *   - bold axis titles
 *   - NO gridlines
 *   - labels drawn inside the bars (not floating tooltips)
 *
 * Pure, DOM-free: builds and returns an SVG string. The caller (a real
 * page) sets `container.innerHTML = svg`; a test can assert on the
 * string directly without a document.
 */

const FONT = "font-family:'Lexend',sans-serif;";
const AXIS_COLOR = '#111111';
const BAR_COLOR = '#1a56db';
const LABEL_COLOR = '#ffffff';

/**
 * @param {{
 *   title: string,
 *   xLabel: string,
 *   yLabel: string,
 *   bars: { label: string, value: number }[],
 *   formatValue?: (n: number) => string,
 *   width?: number,
 *   height?: number,
 * }} opts
 * @returns {string} an <svg>...</svg> string
 */
export function renderBarChartSvg(opts) {
  const {
    title, xLabel, yLabel, bars,
    formatValue = (n) => n.toFixed(2),
    width = 640, height = 340,
  } = opts;

  const margin = { top: 44, right: 20, bottom: 64, left: 64 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;

  const maxValue = Math.max(1e-9, ...bars.map((b) => b.value));
  const tickCount = 4;
  const ticks = Array.from({ length: tickCount + 1 }, (_, i) => (maxValue * i) / tickCount);

  const barGap = bars.length > 0 ? plotW / bars.length : plotW;
  const barWidth = Math.min(64, barGap * 0.6);
  const xLabelFontSize = 11;

  // A value label needs roughly this much vertical room to sit fully
  // inside the bar and stay legible (white text needs a solid blue
  // background behind every pixel of it, not just some).
  const MIN_HEIGHT_FOR_INSIDE_LABEL = 20;

  const barsSvg = bars.map((b, i) => {
    const barHeight = maxValue > 0 ? (b.value / maxValue) * plotH : 0;
    const x = margin.left + i * barGap + (barGap - barWidth) / 2;
    const y = margin.top + plotH - barHeight;
    const labelText = escapeXml(formatValue(b.value));
    let valueLabelSvg;
    if (barHeight >= MIN_HEIGHT_FOR_INSIDE_LABEL) {
      // Room to fit inside the bar: white-on-blue, near the bar's top.
      // Clamped so it can never slide past the axis line (a real bug
      // this chart had: the old clamp let a short bar's label land ON
      // the x-axis and collide with the category label below it).
      const labelY = Math.min(y + 14, margin.top + plotH - 4);
      valueLabelSvg = `<text x="${(x + barWidth / 2).toFixed(1)}" y="${labelY.toFixed(1)}" text-anchor="middle" fill="${LABEL_COLOR}" style="${FONT}font-size:11px;font-weight:600;">${labelText}</text>`;
    } else {
      // Too short for the label to fit on solid bar color (part of it
      // would sit on the white background behind, unreadable white on
      // white). Fall back to dark text just ABOVE the bar instead —
      // still visibly attached to its bar, always legible.
      const labelY = Math.max(y - 4, margin.top + 12);
      valueLabelSvg = `<text x="${(x + barWidth / 2).toFixed(1)}" y="${labelY.toFixed(1)}" text-anchor="middle" fill="${AXIS_COLOR}" style="${FONT}font-size:11px;font-weight:600;">${labelText}</text>`;
    }
    const { text: xLabelText, full: xLabelFull } = fitLabel(b.label, barGap * 0.92, xLabelFontSize);
    return `
      <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barHeight.toFixed(1)}" fill="${BAR_COLOR}" />
      ${valueLabelSvg}
      <g>${xLabelFull !== xLabelText ? `<title>${escapeXml(xLabelFull)}</title>` : ''}<text x="${(x + barWidth / 2).toFixed(1)}" y="${(margin.top + plotH + 16).toFixed(1)}" text-anchor="middle" fill="${AXIS_COLOR}" style="${FONT}font-size:${xLabelFontSize}px;font-weight:300;">${escapeXml(xLabelText)}</text></g>
    `;
  }).join('');

  const yTicksSvg = ticks.map((t) => {
    const y = margin.top + plotH - (t / maxValue) * plotH;
    return `<text x="${(margin.left - 8).toFixed(1)}" y="${(y + 4).toFixed(1)}" text-anchor="end" fill="${AXIS_COLOR}" style="${FONT}font-size:10px;font-weight:300;">${escapeXml(formatValue(t))}</text>`;
  }).join('');

  return `
<svg viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${escapeXml(title)}">
  <text x="${width / 2}" y="22" text-anchor="middle" fill="${AXIS_COLOR}" style="${FONT}font-size:16px;font-weight:600;">${escapeXml(title)}</text>
  <!-- axis lines -->
  <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + plotH}" stroke="${AXIS_COLOR}" stroke-width="1.5" />
  <line x1="${margin.left}" y1="${margin.top + plotH}" x2="${margin.left + plotW}" y2="${margin.top + plotH}" stroke="${AXIS_COLOR}" stroke-width="1.5" />
  ${yTicksSvg}
  ${barsSvg}
  <text x="${(margin.left + plotW / 2).toFixed(1)}" y="${height - 8}" text-anchor="middle" fill="${AXIS_COLOR}" style="${FONT}font-size:12px;font-weight:600;">${escapeXml(xLabel)}</text>
  <text x="14" y="${(margin.top + plotH / 2).toFixed(1)}" text-anchor="middle" fill="${AXIS_COLOR}" style="${FONT}font-size:12px;font-weight:600;" transform="rotate(-90 14 ${(margin.top + plotH / 2).toFixed(1)})">${escapeXml(yLabel)}</text>
</svg>`;
}

/** Shrinks a category label to fit its allotted width, so two adjacent
 * bars' labels (e.g. long Bedrock model ids) never overlap. This is a
 * character-count heuristic, not real text measurement (no canvas is
 * available in this DOM-free module) — it uses an average glyph width
 * for Lexend Light at the given font size, which is conservative enough
 * in practice to avoid collisions without needing a real text-metrics
 * call. Returns the full label too, so the caller can put it in a
 * <title> tooltip when truncated. */
export function fitLabel(label, maxWidthPx, fontSize) {
  const avgCharWidth = fontSize * 0.56;
  const maxChars = Math.max(3, Math.floor(maxWidthPx / avgCharWidth));
  if (label.length <= maxChars) return { text: label, full: label };
  const text = label.slice(0, Math.max(1, maxChars - 1)) + '…';
  return { text, full: label };
}

export function escapeXml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "2026-09-12" -> "Sep 26", per §1.3's "dates as 'Mon YY'". Use this for
 * date labels coarser than daily (e.g. a header caption, or a future
 * monthly rollup) — see formatMonD's doc comment for why the per-day
 * chart/table use a different format. */
export function formatMonYy(isoDate) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  const yy = String(d.getUTCFullYear()).slice(-2);
  return `${MONTH_NAMES[d.getUTCMonth()]} ${yy}`;
}

/** "2026-09-12" -> "Sep 12". D15-style disclosed judgment call: the spec
 * text says dates as "Mon YY", but the cost-PER-DAY chart and its table
 * plot one point per day — with month+year only, every day in the same
 * month renders the identical label ("Sep 26" three times over), which
 * defeats the chart. "Mon YY" is kept (above) for anything coarser than
 * daily; the day-grouped chart/table use "Mon D" instead so each bar and
 * row stays distinguishable. Documented as D16 in CONTEXT.md. */
export function formatMonD(isoDate) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  return `${MONTH_NAMES[d.getUTCMonth()]} ${d.getUTCDate()}`;
}
