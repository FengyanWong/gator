import { useMemo, useState, useSyncExternalStore } from 'react';
import { Json } from '../api';
import { hintedLayout } from './circuitLayout';
import { CIRCUIT_PICTURE_KEY } from '../contract';

/** The circuit picture of the Project column (record 7.158, the user's choice of 2026-10-03: "move 5"). The loaded circuit as
 *  a small node-link drawing in the manner of the circuit graph view - devices as boxes, nets as dots, supply on top and
 *  ground at the bottom - placed by the graph view's own hard-coded hints (circuitLayout.ts: no agent, no model call, the same
 *  circuit always gives the same picture). A second on-screen picture by user decision, under the graph view's terms: it is
 *  drawn from what loading the task already returned (the circuit summary), asks nothing of the backend and writes nothing.
 *  Pointing at a Parameters row (Editors.tsx) lights the devices that row sizes: its own and the rows tied to it. */

// ---- the devices the pointer is on: Editors.tsx says, the picture listens (nothing else re-renders) -------------------------
let pointed: string[] = [];
const listeners = new Set<() => void>();
export function pointAt(paths: string[]) {
  if (paths.length === pointed.length && paths.every((p, i) => p === pointed[i])) return;
  pointed = paths;
  listeners.forEach(listener => listener());
}
const usePointed = () => useSyncExternalStore(listener => { listeners.add(listener); return () => { listeners.delete(listener); }; }, () => pointed);

const SOURCES = ['vsource', 'isource'];
const FAMILY: Record<string, string> = { nmos: 'nmos', pmos: 'pmos', resistor: 'passive', capacitor: 'passive', varactor: 'passive', inductor: 'passive',
  diode: 'passive', vsource: 'source', isource: 'source' };
const GROUND = /^(0|gnd!?|vss!?|ground)$/i;
const CONDUCTING = (role: string) => !['gate', 'base', 'bulk'].includes(role);
const W = 276, PAD = 18, MAX_H = 300;

type Point = { x: number; y: number };
type Graph = { devices: Json[]; nets: Json[]; connections: Json[]; names: Record<string, string> };

/** What the picture draws: the DUT's devices (else every device but the testbench's sources), the nets they touch and their
 *  connections. A rail the circuit does not mark itself is found as a reader finds it: ground by its name, the supply as a
 *  net that a voltage source holds against ground and that devices conduct from (a net that only drives gates is a bias). */
export function pictureGraph(summary: Json): Graph | null {
  const all: Json[] = summary?.devices ?? [];
  const dut = typeof summary?.dut_hierarchy === 'string' ? summary.dut_hierarchy.replace(/\/+$/, '') : '';
  let devices = dut ? all.filter(d => String(d.instance_path).startsWith(`${dut}/`)) : [];
  if (!devices.length) devices = all.filter(d => !SOURCES.includes(d.kind));
  if (!devices.length) return null;
  const roles: Record<string, string[]> = Object.fromEntries((summary.nets ?? []).map((n: Json) => [n.net, n.roles ?? []]));
  const connections = devices.flatMap(d => (d.terminals ?? []).filter((t: Json) => t.net)
    .map((t: Json) => ({ device: d.instance_path, net: t.net, role: t.role ?? 'normal', terminal: t.terminal })));
  const used = [...new Set(connections.map(c => c.net as string))];
  let ground = used.filter(n => roles[n]?.includes('ground'));
  if (!ground.length) ground = used.filter(n => GROUND.test(n));
  let supply = used.filter(n => roles[n]?.includes('supply'));
  if (!supply.length) {
    const held = new Set<string>();
    for (const source of all) if (source.kind === 'vsource') {
      const ends: string[] = (source.terminals ?? []).map((t: Json) => t.net);
      const isGround = (n: string) => ground.includes(n) || GROUND.test(n);
      if (ends.length === 2 && ends.some(isGround)) ends.filter(n => !isGround(n)).forEach(n => held.add(n));
    }
    supply = used.filter(n => held.has(n) && connections.some(c => c.net === n && CONDUCTING(c.role)));
  }
  // A name is drawn without its hierarchy ("DUT/M1" is M1, "DUT/GP" is GP) unless two would then read the same.
  const last = (id: string) => id.slice(id.lastIndexOf('/') + 1);
  const shortened = (ids: string[], kind: string) => {
    const count: Record<string, number> = {};
    for (const id of ids) count[last(id)] = (count[last(id)] ?? 0) + 1;
    return ids.map(id => [`${kind}:${id}`, count[last(id)] === 1 ? last(id) : id]);
  };
  const names = Object.fromEntries([...shortened(used, 'n'), ...shortened(devices.map(d => d.instance_path), 'd')]);
  return {
    devices: devices.map(d => ({ id: d.instance_path, kind: d.kind, family: d.kind, model: d.model })),
    nets: used.map(n => ({ id: n, roles: supply.includes(n) ? ['supply'] : ground.includes(n) ? ['ground'] : roles[n]?.length ? roles[n] : ['normal'] })),
    connections, names,
  };
}

/** Where everything stands, in the picture's own pixels: the graph view's hints, else a ring (a circuit with no rails). */
function placed(graph: Graph): { at: Record<string, Point>; height: number } {
  const ids = [...graph.devices.map(d => `d:${d.id}`), ...graph.nets.map(n => `n:${n.id}`)];
  const raw: Record<string, Point> = hintedLayout(graph)
    ?? Object.fromEntries(ids.map((id, i) => [id, { x: 400 * Math.cos(2 * Math.PI * i / ids.length), y: 400 * Math.sin(2 * Math.PI * i / ids.length) }]));
  const points = ids.map(id => raw[id]).filter(Boolean);
  const minX = Math.min(...points.map(p => p.x)), maxX = Math.max(...points.map(p => p.x));
  const minY = Math.min(...points.map(p => p.y)), maxY = Math.max(...points.map(p => p.y));
  // Across: the column's width. Down: about as tall as wide per step, within the height the column can spare.
  const kx = (W - 2 * PAD) / Math.max(1, maxX - minX), ky = Math.min((MAX_H - 2 * PAD) / Math.max(1, maxY - minY), Math.max(kx, 0.3));
  const at: Record<string, Point> = {};
  for (const id of ids) if (raw[id]) at[id] = { x: PAD + (raw[id].x - minX) * kx, y: PAD + (raw[id].y - minY) * ky };
  return { at, height: Math.round((maxY - minY) * ky + 2 * PAD) };
}

const isRail = (net: Json) => (net.roles as string[]).some(r => r === 'supply' || r === 'ground');
const familyOf = (d: Json) => FAMILY[d.family] ?? 'other';
/** A device's box: wide enough for its name. */
const boxOf = (d: Json, label: string) => ({ w: Math.max(familyOf(d) === 'passive' ? 22 : 24, label.length * 5.4 + 8), h: familyOf(d) === 'passive' ? 12 : 14 });

/** Where each net's name goes: right of its dot, else left, below or above - the first place that covers no box, dot or
 *  name already placed (8.5 px letters are about 5.1 px wide). */
function netLabels(graph: Graph, at: Record<string, Point>) {
  const short = (key: string) => graph.names[key] ?? key.slice(2);
  type Box = { x0: number; x1: number; y0: number; y1: number };
  const taken: Box[] = [];
  for (const d of graph.devices) { const p = at[`d:${d.id}`]; if (!p) continue; const { w, h } = boxOf(d, short(`d:${d.id}`)); taken.push({ x0: p.x - w / 2, x1: p.x + w / 2, y0: p.y - h / 2, y1: p.y + h / 2 }); }
  for (const n of graph.nets) { const p = at[`n:${n.id}`]; if (!p) continue; const r = isRail(n) ? 5.5 : 3.6; taken.push({ x0: p.x - r, x1: p.x + r, y0: p.y - r, y1: p.y + r }); }
  const free = (b: Box) => b.x0 >= 0 && b.x1 <= W && !taken.some(t => b.x0 < t.x1 && b.x1 > t.x0 && b.y0 < t.y1 && b.y1 > t.y0);
  const out: Record<string, { x: number; y: number; anchor: 'start' | 'end' | 'middle' }> = {};
  for (const n of graph.nets) {
    const p = at[`n:${n.id}`]; if (!p) continue;
    const r = isRail(n) ? 5.5 : 3.6, w = short(`n:${n.id}`).length * 5.1, gap = r + 3;
    const options = [
      { x: p.x + gap, y: p.y, anchor: 'start' as const, box: { x0: p.x + gap, x1: p.x + gap + w, y0: p.y - 5, y1: p.y + 5 } },
      { x: p.x - gap, y: p.y, anchor: 'end' as const, box: { x0: p.x - gap - w, x1: p.x - gap, y0: p.y - 5, y1: p.y + 5 } },
      { x: p.x, y: p.y + r + 7, anchor: 'middle' as const, box: { x0: p.x - w / 2, x1: p.x + w / 2, y0: p.y + r + 2, y1: p.y + r + 12 } },
      { x: p.x, y: p.y - r - 7, anchor: 'middle' as const, box: { x0: p.x - w / 2, x1: p.x + w / 2, y0: p.y - r - 12, y1: p.y - r - 2 } },
    ];
    const chosen = options.find(o => free(o.box)) ?? options.find(o => o.box.x0 >= 0 && o.box.x1 <= W) ?? options[0];
    taken.push(chosen.box);
    out[n.id] = { x: chosen.x, y: chosen.y, anchor: chosen.anchor };
  }
  return out;
}

export function CircuitPicture({ circuit }: { circuit: Json }) {
  // Folded at first, like every block of the Project column (the user's rule); opened once, it stays open in this browser.
  const [open, setOpen] = useState(() => { try { return localStorage.getItem(CIRCUIT_PICTURE_KEY) === 'open'; } catch { return false; } });
  const graph = useMemo(() => (circuit?.loaded ? pictureGraph(circuit.summary) : null), [circuit]);
  const layout = useMemo(() => {
    if (!graph) return null;
    const short = (key: string) => graph.names[key] ?? key.slice(2);
    const { at, height } = placed(graph);
    return { at, height, short, labels: netLabels(graph, at) };
  }, [graph]);
  const lit = new Set(usePointed());
  if (!graph || !layout) return null;
  const { at, height, short, labels } = layout;
  const roleOf = (net: Json) => (net.roles as string[]).find(r => r !== 'normal') ?? 'normal';
  return (
    <details className="section circuit-picture" open={open}
      onToggle={e => { const now = e.currentTarget.open; setOpen(now); try { localStorage.setItem(CIRCUIT_PICTURE_KEY, now ? 'open' : 'closed'); } catch { /* not remembered */ } }}>
      <summary><h3>Circuit picture</h3> <span className="hint">{graph.devices.length} devices · {graph.nets.length} nets</span></summary>
      <svg viewBox={`0 0 ${W} ${height}`} role="img"
        aria-label={`The circuit as a picture: ${graph.devices.length} devices and ${graph.nets.length} nets, supply at the top and ground at the bottom.`}>
        {graph.connections.filter(c => c.role !== 'bulk').map((c, i) => {
          const a = at[`d:${c.device}`], b = at[`n:${c.net}`];
          if (!a || !b) return null;
          const on = lit.has(c.device) ? ' on' : '', gate = !CONDUCTING(c.role);
          return <g key={i}><line className={`cp-link${gate ? ' gate' : ''}${on}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
            {gate && <circle className={`cp-gate-dot${on}`} cx={a.x + (b.x - a.x) * 0.18} cy={a.y + (b.y - a.y) * 0.18} r={1.8} />}</g>;
        })}
        {graph.nets.map(n => {
          const p = at[`n:${n.id}`], label = labels[n.id]; if (!p || !label) return null;
          const role = roleOf(n);
          return <g key={n.id} className={`cp-net ${role}`}><title>{`net ${n.id}${role !== 'normal' ? ` (${role})` : ''}`}</title>
            <circle cx={p.x} cy={p.y} r={isRail(n) ? 5.5 : 3.6} />
            <text x={label.x} y={label.y} textAnchor={label.anchor}>{short(`n:${n.id}`)}</text></g>;
        })}
        {graph.devices.map(d => {
          const p = at[`d:${d.id}`]; if (!p) return null;
          const family = familyOf(d), label = short(`d:${d.id}`), on = lit.has(d.id), { w, h } = boxOf(d, label);
          return <g key={d.id} className={`cp-dev ${family}${on ? ' on' : ''}`}>
            <title>{`${d.id} · ${d.kind}${d.model ? ` · ${d.model}` : ''}`}</title>
            {on && <rect className="halo" x={p.x - w / 2 - 4} y={p.y - h / 2 - 4} width={w + 8} height={h + 8} rx={7} />}
            {family === 'source'
              ? <polygon className="body" points={`${p.x - w / 2 + 4},${p.y - h / 2} ${p.x + w / 2 - 4},${p.y - h / 2} ${p.x + w / 2},${p.y} ${p.x + w / 2 - 4},${p.y + h / 2} ${p.x - w / 2 + 4},${p.y + h / 2} ${p.x - w / 2},${p.y}`} />
              : <rect className="body" x={p.x - w / 2} y={p.y - h / 2} width={w} height={h} rx={family === 'passive' ? 6 : 3} />}
            <text x={p.x} y={p.y}>{label}</text></g>;
        })}
      </svg>
      {circuit.summary?.truncated && <p className="hint">The circuit summary lists part of this circuit only: the picture shows that part.</p>}
      <p className="hint picture-hint">Point at a Parameters row: the devices it sizes light up.</p>
    </details>);
}
