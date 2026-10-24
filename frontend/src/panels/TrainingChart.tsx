import { useEffect, useMemo, useRef, useState } from 'react';
import type uPlotType from 'uplot';
import 'uplot/dist/uPlot.min.css';
import type { Built, Category, Series } from './trainingData';

/** One chart of the Training tab (record 7.193), drawn with uPlot in the browser only - nothing drawn is written anywhere.
 *  The chart is made once and fed new data (setData) while its series stay the same; a new chart only when the series
 *  change (another chart chosen, smoothing on or off, a category appearing). It is destroyed when the
 *  tab goes away or the run changes. uPlot itself is loaded the first time a chart is drawn, like cytoscape for the graph
 *  view: a page that never opens the Training tab never loads it.
 *
 *  Zoom is the user's: dragging across the plot selects an x range (`onZoom`), a double click or Reset zoom shows the whole
 *  run (`onReset`). The values under the pointer - and, without a pointer, the newest ones - are written into the line
 *  above the plot without drawing the page again. */
type UPlot = uPlotType;
type UPlotClass = typeof uPlotType;
let loading: Promise<UPlotClass> | null = null;
const loadUPlot = () => {
  if (!loading) loading = import('uplot').then(m => m.default).catch(e => { loading = null; throw e; });
  return loading;
};

export type Format = (value: number) => string;
export interface ChartProps {
  built: Built | null; hidden: boolean; xLabel: string;
  format: Format;                               // a y value with the chart's unit
  describe: (row: number) => string;            // the facts of a recorded row, for the readout
  onZoom: (min: number, max: number) => void; onReset: () => void;
  onWidth: (width: number) => void;             // the plot's width: the data is thinned to one point group per pixel column
}

/** A colour of the page by name, as canvas drawing needs it (styles.css holds them). */
function token(element: HTMLElement, name: string, fallback: string) {
  return getComputedStyle(element).getPropertyValue(name).trim() || fallback;
}
function alpha(color: string, a: number) {
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(color)?.[1];
  if (hex) {
    const full = hex.length === 3 ? hex.split('').map(c => c + c).join('') : hex;
    return `rgba(${parseInt(full.slice(0, 2), 16)}, ${parseInt(full.slice(2, 4), 16)}, ${parseInt(full.slice(4, 6), 16)}, ${a})`;
  }
  const rgb = /^rgba?\(([^)]+)\)$/.exec(color)?.[1]?.split(',').map(s => s.trim());
  return rgb ? `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${a})` : color;
}

interface Palette { training: string; evaluation: string; start: string; other: string[]; runs: string[]; limit: string; superseded: string; text: string; muted: string; grid: string; line: string; bad: string; label: string; mono: string }
function palette(element: HTMLElement): Palette {
  // The series colours in order (record 7.360): red, white, blue, violet; amber stays the limits'.
  const series = ['--series-1', '--series-2', '--series-3', '--series-4'].map((name, i) => token(element, name, ['#f5434f', '#e8e8ec', '#4fb3ff', '#c08cff'][i]));
  return { training: series[0], evaluation: series[1], start: token(element, '--muted', '#a9a9b0'),
    other: [series[0], series[2]], limit: token(element, '--warn', '#f2b53f'),
    // compared runs (record 7.200): the shown run first, the others in the series' order
    runs: series,
    superseded: token(element, '--muted', '#a9a9b0'), text: token(element, '--text', '#f4f4f5'), muted: token(element, '--muted', '#a9a9b0'),
    grid: token(element, '--grid-line', '#1c1c20'), line: token(element, '--line', '#2c2c31'), bad: token(element, '--bad', '#ff4f61'),
    label: token(element, '--f-label', 'sans-serif'), mono: token(element, '--f-mono', 'monospace') };
}

/** The colour of a series: its category's, or for the learner's series the n-th of `other`. */
function colourOf(series: Series, index: number, colours: Palette) {
  if (series.role === 'limit') return colours.limit;
  if (series.role === 'superseded') return colours.superseded;
  if (series.run != null) return colours.runs[series.run % colours.runs.length];
  if (series.category) return colours[series.category as Category];
  return colours.other[index % colours.other.length];
}

/** What a series group is called on its toggle: the category, or the learner series' own name. */
export const groupOf = (series: Series) => (series.role === 'limit' ? 'limits' : series.role === 'superseded' ? 'abandoned' : series.run != null ? `run${series.run}`
  : series.category ?? series.label.replace(/ \(recorded\)$|: mean of last \d+( evaluations)?$/, ''));

export function TrainingChart({ built, hidden, xLabel, format, describe, onZoom, onReset, onWidth }: ChartProps) {
  const box = useRef<HTMLDivElement>(null);
  const readout = useRef<HTMLDivElement>(null);
  const plot = useRef<UPlot | null>(null);
  const layout = useRef('');                                       // the series the chart was made for
  const latest = useRef({ built, format, describe, onZoom, onReset, onWidth });
  latest.current = { built, format, describe, onZoom, onReset, onWidth };
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [failed, setFailed] = useState<string | null>(null);
  const [off, setOff] = useState<Set<string>>(() => new Set());     // series groups switched off on the toggles
  const offRef = useRef(off);
  offRef.current = off;
  const steady = useRef({ width: -1, height: 0 });                  // the readout's tallest at its width (branch record SIF-120)

  // The plot follows its box. A hidden tab measures 0 x 0: kept as it was, so nothing is drawn into nothing.
  useEffect(() => {
    const element = box.current;
    if (!element) return;
    const observer = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      if (width > 0 && height > 0) {
        setSize(s => (Math.abs(s.width - width) < 1 && Math.abs(s.height - height) < 1 ? s : { width: Math.floor(width), height: Math.floor(height) }));
        latest.current.onWidth(Math.floor(width));
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => () => { plot.current?.destroy(); plot.current = null; layout.current = ''; }, []);

  // The values under the pointer, or the newest ones: written straight into the line above the plot.
  const showReadout = (u: UPlot | null) => {
    const element = readout.current, data = latest.current.built;
    if (!element) return;
    if (!u || !data || !data.x.length) { element.textContent = ''; return; }
    const hovering = u.cursor.left != null && u.cursor.left >= 0;
    // the row under the pointer, and only the values recorded AT it (a row has one category: the other series have none there).
    // Rows that share its x count as it: compared runs learning 8 and 1 times per evaluation have 8 and 1 rows at one x (7.213).
    const index = hovering ? Math.min(data.x.length - 1, Math.max(0, u.posToIdx(u.cursor.left!))) : data.x.length - 1;
    const parts: [string, string][] = [];
    data.series.forEach((series, i) => {
      if (series.role === 'limit' || !u.series[i + 1]?.show) return;
      let value = series.values[index];
      for (let j = index - 1; value === undefined && j >= 0 && data.x[j] === data.x[index]; j--) value = series.values[j];
      for (let j = index + 1; value === undefined && j < data.x.length && data.x[j] === data.x[index]; j++) value = series.values[j];
      if (value === undefined) return;
      parts.push([series.label, value === null ? 'no value' : latest.current.format(value)]);
    });
    const row = data.rows[index];      // -1 on a comparison: several runs' rows share an x, none of them is named
    // The values first, then the row's phase and episode (branch record SIF-7: the line was cut at the chart's width, and the
    // values came last - "Newest: Evaluation 800 · search · episode 1-000189 step 4 · Training (recorded) 0.06274 · Training: me...").
    // The numbers in the text colour, the words muted (branch record SIF-25): the eye finds a value; the line's text is the same.
    // It wraps rather than being cut (branch record SIF-120: at 1680 px it still lost the row's facts, "... · search · episo...",
    // at 1366 px a value too): each part - the x, a series with its value, a fact of the row - is a box of its own
    // (roadster.css), so the line breaks between them and a value never starts a line apart from its name. Its text is the
    // same, so it needs no tooltip to show the whole any more.
    const doc = element.ownerDocument;
    const value = (text: string) => { const b = doc.createElement('b'); b.textContent = text; return b; };
    const part = (...children: (Node | string)[]) => { const span = doc.createElement('span'); span.className = 'readout-part'; span.append(...children); return span; };
    const pieces = [part(`${hovering ? '' : 'Newest: '}${xLabel} `, value(String(data.x[index]))), ...parts.map(([label, text]) => part(`${label} `, value(text)))];
    if (row != null && row >= 0) pieces.push(...latest.current.describe(row).split(' · ').filter(Boolean).map(fact => part(fact)));
    element.replaceChildren(...pieces.flatMap((piece, i) => (i ? [' · ', piece] : [piece])));
    // A row with fewer values must not shorten the line under a moving pointer (SIF-120): the plot under it would grow and
    // shrink as the pointer crossed the rows - a training row's two lines, an episode start's one. The line keeps the most
    // lines it has taken at its width, until its width or the chart's series change.
    const width = element.clientWidth;
    if (width !== steady.current.width) { steady.current = { width, height: 0 }; element.style.minHeight = ''; }
    const height = element.offsetHeight;
    if (height > steady.current.height) { steady.current.height = height; element.style.minHeight = `${height}px`; }
  };

  const layoutKey = useMemo(() => (built ? `${built.axis}|${built.unit}|${built.series.map(s => `${s.role}:${s.label}:${s.category}`).join('|')}` : ''), [built]);

  useEffect(() => {
    if (hidden || !built || !box.current || size.width < 60 || size.height < 60) return;
    let cancelled = false;
    loadUPlot().then(UPlotClass => {
      if (cancelled || !box.current) return;
      setFailed(null);
      const data = [built.x, ...built.series.map(s => s.values)] as uPlotType.AlignedData;
      if (!plot.current || layout.current !== layoutKey) {
        plot.current?.destroy();
        plot.current = new UPlotClass(options(UPlotClass, built, box.current, size, xLabel), data, box.current);
        layout.current = layoutKey;
        steady.current = { width: -1, height: 0 };                     // other series: the readout measures its lines anew
        built.series.forEach((s, i) => { if (offRef.current.has(groupOf(s))) plot.current!.setSeries(i + 1, { show: false }); });
      } else {
        if (plot.current.width !== size.width || plot.current.height !== size.height) plot.current.setSize(size);
        plot.current.setData(data, false);
      }
      if (built.range) plot.current.setScale('x', { min: built.range[0], max: built.range[1] });
      showReadout(plot.current);
    }).catch(e => { if (!cancelled) setFailed(`The chart could not be drawn: ${String(e?.message ?? e)}`); });
    return () => { cancelled = true; };
  }, [built, layoutKey, hidden, size.width, size.height]);

  /** The chart's options: the page's colours, our zoom and reset, the markers drawn over the plot. */
  function options(UPlotClass: UPlotClass, data: Built, element: HTMLElement, { width, height }: { width: number; height: number }, label: string): uPlotType.Options {
    const colours = palette(element);
    // the axis numbers at 12 px, beside the readout's 12 px (branch record SIF-65: 11 px). A whole number: uPlot multiplies the
    // digits before "px" by the screen's pixel ratio, so "12.5px" would draw "12.10px" on a screen of twice the pixels. The y
    // axis's 64 px still hold "1.28 GHz".
    const font = `12px ${colours.label}`;
    const axis = (y: boolean): uPlotType.Axis => ({ stroke: colours.muted, font, labelFont: font, size: y ? 64 : 34,
      grid: { stroke: colours.grid, width: 1 }, ticks: { stroke: colours.line, width: 1, size: 4 },
      ...(y ? { values: (_u: UPlot, splits: number[]) => splits.map(v => latest.current.format(v)) }
        : { label, labelSize: 14, incrs: [1, 2, 5, 10, 20, 50, 100, 200, 500, 1e3, 2e3, 5e3, 1e4, 2e4, 5e4, 1e5, 2e5, 5e5, 1e6, 2e6, 5e6],
          values: (_u: UPlot, splits: number[]) => splits.map(v => String(v)) }) });
    const order = [...new Set(data.series.map(groupOf))];             // the learner's series take the series colours in turn
    const series: uPlotType.Series[] = [{ label }, ...data.series.map((s): uPlotType.Series => {
      const colour = colourOf(s, order.indexOf(groupOf(s)), colours);
      const dense = data.axis === 'update';
      if (s.role === 'limit') return { label: s.label, stroke: colour, width: 1.25, dash: [6, 4], points: { show: false } };
      if (s.role === 'superseded') return { label: s.label, stroke: alpha(colour, 0.8), width: 1, dash: [3, 3], points: { show: false } };
      const dash = s.dash ? { dash: [5, 3] } : {};
      if (s.role === 'smooth') return { label: s.label, stroke: colour, width: 2, ...dash, points: { show: false } };
      if (s.role === 'line') return { label: s.label, stroke: colour, width: 2, paths: UPlotClass.paths.stepped!({ align: 1 }), points: { show: false } };
      // a recorded value: under a smoothed line faint points (thousands of learner updates: a faint thin line), alone a thin line
      // with its points; an episode start (one design re-simulated now and then) points only - a line through them would look
      // like a limit
      const smoothed = data.series.some(o => o.role === 'smooth' && o.category === s.category && groupOf(o) === groupOf(s));
      const pointsOnly = (smoothed && !dense) || s.category === 'start';
      return { label: s.label, stroke: alpha(colour, smoothed ? 0.35 : 0.85), width: 1, ...dash, ...(pointsOnly ? { paths: () => null } : {}),
        points: { show: dense ? undefined : true, size: s.category === 'start' ? 4 : 3, stroke: alpha(colour, smoothed ? 0.45 : 0.9), fill: alpha(colour, smoothed ? 0.3 : 0.6), width: 1 } };
    })];
    const share = data.unit === 'share';
    return {
      width, height, legend: { show: false }, series, axes: [axis(false), axis(true)],
      scales: { x: { time: false }, y: share ? { range: [-0.05, 1.05] } : {} },
      cursor: { y: false, drag: { x: true, y: false, setScale: false }, points: { size: 6 },
        bind: { dblclick: () => () => { latest.current.onReset(); return null; } } },
      hooks: {
        setSelect: [u => {
          if (u.select.width > 2) {
            const min = u.posToVal(u.select.left, 'x'), max = u.posToVal(u.select.left + u.select.width, 'x');
            if (max > min) latest.current.onZoom(min, max);
          }
          u.setSelect({ left: 0, top: 0, width: 0, height: 0 }, false);
        }],
        setCursor: [u => showReadout(u)],
        draw: [u => drawMarks(u, colours)],
      },
    };
  }
  /** Markers over the plot: where the run continued after a pause, where the learner restarted from a save point, and a
   *  shade over history that the page thinned to its extremes (memory bound). */
  function drawMarks(u: UPlot, colours: Palette) {
    const data = latest.current.built;
    if (!data) return;
    const ctx = u.ctx, { left, top, width, height } = u.bbox, ratio = devicePixelRatio || 1;
    ctx.save();
    if (data.thinnedTo != null && data.extent) {
      const from = Math.max(left, u.valToPos(data.extent[0], 'x', true)), to = Math.min(left + width, u.valToPos(data.thinnedTo, 'x', true));
      if (to > from) { ctx.fillStyle = alpha(colours.muted, 0.08); ctx.fillRect(from, top, to - from, height); }
    }
    ctx.font = `${10 * ratio}px ${colours.label}`;
    for (const mark of data.markers) {
      const x = Math.round(u.valToPos(mark.x, 'x', true));
      if (x < left || x > left + width) continue;
      ctx.strokeStyle = mark.kind === 'restart' ? colours.bad : colours.muted;
      ctx.fillStyle = ctx.strokeStyle;
      ctx.setLineDash([4 * ratio, 3 * ratio]); ctx.lineWidth = ratio;
      ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, top + height); ctx.stroke();
      ctx.fillText(mark.label, x + 3 * ratio, top + 11 * ratio);
    }
    ctx.restore();
  }

  const groups = useMemo(() => {
    const seen = new Map<string, { label: string; key: string }>();
    for (const s of built?.series ?? []) {
      const group = groupOf(s);
      if (seen.has(group)) continue;
      const key = s.role === 'limit' ? 'limit' : s.role === 'superseded' ? 'superseded' : s.run != null ? `run${s.run % 4}` : s.category ?? `other${seen.size % 2}`;   // its colour, as colourOf picks it
      seen.set(group, { key, label: s.role === 'limit' ? 'limit' : s.role === 'superseded' ? 'abandoned at a restart'
        : s.label.replace(/ \(recorded\)$|: mean of last \d+$| \(each design\)$|: share so far$/, '').replace(s.run != null ? / \/ [^/]+$/ : /$^/, '') });
    }
    return [...seen.entries()];
  }, [built]);
  const toggle = (group: string) => {
    const next = new Set(off);
    if (next.has(group)) next.delete(group); else next.add(group);
    setOff(next);
    built?.series.forEach((s, i) => { if (groupOf(s) === group) plot.current?.setSeries(i + 1, { show: !next.has(group) }); });
    showReadout(plot.current);
  };

  return (<div className="training-plot-area">
    <div className="training-legend">
      {groups.map(([group, g]) => <button key={group} type="button" className={`training-key key-${g.key}${off.has(group) ? ' off' : ''}`} aria-pressed={!off.has(group)}
        onClick={() => toggle(group)} title={`${off.has(group) ? 'Show' : 'Hide'} ${g.label}`}><span className="swatch" />{g.label}</button>)}
      <div className="training-readout" ref={readout} />
    </div>
    <div className="training-plot" ref={box}>{failed && <p className="error">{failed}</p>}</div>
  </div>);
}

