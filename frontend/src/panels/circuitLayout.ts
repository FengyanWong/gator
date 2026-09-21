import { Json } from '../api';

// WHERE the nodes of the circuit graph view stand - nothing else. The view is a node-link picture of the graph the
// network sees (devices and nets as nodes, connections as straight links), NOT a schematic: no symbols, no rails, no
// wire routing (user, 2026-09-21: "don't generate schematic ... graph neural network style like the cytoscape original
// but with some hints from the circuit information"). The drawing package's own layouts know nothing about circuits and
// gave long diagonals and crossings; these HARD-CODED rules (no agent, no model call, same circuit -> same picture) use
// what the graph already says - device kinds, net roles, terminal roles - as hints for the positions:
//   * supply nets at the top, ground nets at the bottom;
//   * a net's height is its place on the DC current path: (device steps from the supply) / (steps from the supply + from
//     ground), walking only through conducting terminals - never through a gate, a bulk tie, another rail or a capacitor;
//     a device stands between the nets it conducts between, so what hangs on the supply is high and what stands on ground low;
//   * nets that only drive gates (inputs, bias) stand beside the devices they drive, a source feeding such a net next to
//     it, a supply source at the side, a capacitor beside the net it loads - none of them takes a place in the rows;
//   * two devices that share two or more nets (the two transistors of an inverter) stand above each other;
//   * left-to-right order by barycentre sweeps (fewer crossings); nothing is put where something already stands, and a
//     node that stands beside the rows is never put where its straight link would run THROUGH another node (it would
//     read as a connection to that node).
// A graph without a supply AND a ground net has no such hints: the caller falls back to the package's layered layout.

export type Point = { x: number; y: number };

const ROW = 112, COLUMN = 214, SOURCES = ['vsource', 'isource'];
export const conducting = (role: string) => role !== 'gate' && role !== 'bulk';
const roleOf = (net: Json): string => (net.roles as string[]).find(r => r !== 'normal') ?? 'normal';
const mean = (values: number[]) => values.reduce((a, b) => a + b, 0) / values.length;

/** Half width / half height of a drawn node, with a little air: a device is a box with its words in it, a net a small circle. */
const half = (id: string) => id[0] === 'd' ? { w: 62, h: 27 } : { w: 22, h: 18 };
/** Does the straight link a-b run through the box of the node `id` standing at q? (Liang-Barsky clipping) */
function through(a: Point, b: Point, q: Point, id: string): boolean {
  const { w, h } = half(id), dx = b.x - a.x, dy = b.y - a.y;
  let enter = 0, leave = 1;
  for (const [delta, low, high] of [[dx, q.x - w - a.x, q.x + w - a.x], [dy, q.y - h - a.y, q.y + h - a.y]]) {
    if (delta === 0) { if (low > 0 || high < 0) return false; continue; }
    const first = Math.min(low / delta, high / delta), second = Math.max(low / delta, high / delta);
    enter = Math.max(enter, first); leave = Math.min(leave, second);
    if (enter > leave) return false;
  }
  return true;
}

export function hintedLayout(view: Json): Record<string, Point> | null {
  const supply: string[] = view.nets.filter((n: Json) => roleOf(n) === 'supply').map((n: Json) => n.id);
  const ground: string[] = view.nets.filter((n: Json) => roleOf(n) === 'ground').map((n: Json) => n.id);
  if (!supply.length || !ground.length) return null;
  const rail = new Set([...supply, ...ground]);
  const kind: Record<string, string> = Object.fromEntries(view.devices.map((d: Json) => [d.id, d.kind]));
  const wires: Json[] = view.connections;
  const conductsAt: Record<string, string[]> = {}, gates: Record<string, string[]> = {}, devicesOn: Record<string, string[]> = {};
  const pathAt: Record<string, string[]> = {}, pathOn: Record<string, string[]> = {};          // the DC current path: conducting terminals, no capacitors
  for (const w of wires) {
    if (conducting(w.role)) {
      (conductsAt[w.device] ??= []).push(w.net); (devicesOn[w.net] ??= []).push(w.device);
      if (kind[w.device] !== 'capacitor') { (pathAt[w.device] ??= []).push(w.net); (pathOn[w.net] ??= []).push(w.device); }
    } else if (w.role === 'gate') (gates[w.net] ??= []).push(w.device);
  }
  // Device steps from a set of rails. A path may END at another rail but never runs through one.
  const steps = (start: string[]) => {
    const found: Record<string, number> = Object.fromEntries(start.map(n => [n, 0])), queue = [...start];
    while (queue.length) {
      const net = queue.shift()!;
      if (rail.has(net) && !start.includes(net)) continue;
      for (const device of pathOn[net] ?? []) for (const other of pathAt[device] ?? [])
        if (found[other] === undefined) { found[other] = found[net] + 1; queue.push(other); }
    }
    return found;
  };
  const fromSupply = steps(supply), fromGround = steps(ground);

  // ---- heights (0 = supply, 1 = ground) ----------------------------------------------------------------------------------
  const level: Record<string, number> = {};
  const isControl = (net: string) => !rail.has(net) && !!gates[net]?.length && (fromSupply[net] === undefined || fromGround[net] === undefined)
    && (devicesOn[net] ?? []).every(d => SOURCES.includes(kind[d]));
  for (const n of view.nets) {
    const s = fromSupply[n.id], g = fromGround[n.id];
    if (rail.has(n.id) || isControl(n.id)) continue;
    level[`n:${n.id}`] = s !== undefined && g !== undefined ? s / (s + g) : s !== undefined ? s / (s + 2) : g !== undefined ? 1 - g / (g + 2) : 0.5;
  }
  const railLevel = (net: string) => supply.includes(net) ? 0 : 1;
  const control: string[] = view.nets.filter((n: Json) => isControl(n.id)).map((n: Json) => n.id);
  const sources: string[] = view.devices.filter((d: Json) => SOURCES.includes(d.kind) && (conductsAt[d.id] ?? []).every(n => rail.has(n) || control.includes(n))).map((d: Json) => d.id);
  const hanging: string[] = view.devices.filter((d: Json) => d.kind === 'capacitor').map((d: Json) => d.id);
  for (const d of view.devices) {
    const known = (conductsAt[d.id] ?? []).map(n => rail.has(n) ? railLevel(n) : level[`n:${n}`]).filter(v => v !== undefined);
    level[`d:${d.id}`] = known.length ? mean(known) : 0.5;
  }

  // ---- rows: heights that are (nearly) equal share a row ------------------------------------------------------------------------
  const core = [...view.devices.filter((d: Json) => !sources.includes(d.id) && !hanging.includes(d.id)).map((d: Json) => `d:${d.id}`),
    ...view.nets.filter((n: Json) => !rail.has(n.id) && !control.includes(n.id)).map((n: Json) => `n:${n.id}`)];
  const sorted = [...core].sort((a, b) => level[a] - level[b]);
  const rowOf: Record<string, number> = {};
  let row = -1, rowStart = -1;
  for (const id of sorted) { if (row < 0 || level[id] - rowStart > 0.07) { row++; rowStart = level[id]; } rowOf[id] = row; }
  const rows: string[][] = Array.from({ length: row + 1 }, () => []);

  // ---- left-to-right: a first order by walking the graph, then barycentre sweeps ------------------------------------------------
  const links: Record<string, { to: string; weight: number }[]> = {};
  for (const w of wires) {
    if (rail.has(w.net) || control.includes(w.net) || sources.includes(w.device) || hanging.includes(w.device) || w.role === 'bulk') continue;
    const a = `d:${w.device}`, b = `n:${w.net}`, weight = conducting(w.role) ? 2 : 1;
    (links[a] ??= []).push({ to: b, weight }); (links[b] ??= []).push({ to: a, weight });
  }
  // Two devices that share two or more nets belong above each other; a ring has no natural left-to-right order, so they are tied directly.
  const shared: Record<string, Set<string>> = {};
  for (const w of wires) if (!rail.has(w.net) && core.includes(`d:${w.device}`)) (shared[w.net] ??= new Set()).add(`d:${w.device}`);
  const together: Record<string, number> = {};
  for (const members of Object.values(shared)) { const list = [...members]; for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
    const key = [list[i], list[j]].sort().join('|'); together[key] = (together[key] ?? 0) + 1; } }
  for (const [key, count] of Object.entries(together)) if (count >= 2) { const [a, b] = key.split('|'); (links[a] ??= []).push({ to: b, weight: 6 }); (links[b] ??= []).push({ to: a, weight: 6 }); }
  const order: string[] = [], seen = new Set<string>();
  const walk = (id: string) => { if (seen.has(id)) return; seen.add(id); order.push(id); for (const l of [...(links[id] ?? [])].sort((p, q) => q.weight - p.weight)) walk(l.to); };
  for (const w of wires) if (supply.includes(w.net) && core.includes(`d:${w.device}`)) walk(`d:${w.device}`);
  for (const id of core) walk(id);
  const x: Record<string, number> = {};
  for (const id of order) { rows[rowOf[id]].push(id); x[id] = (rows[rowOf[id]].length - 1) * COLUMN; }
  const gap = (a: string, b: string) => a[0] === 'd' && b[0] === 'd' ? COLUMN : a[0] === 'n' && b[0] === 'n' ? COLUMN * 0.55 : COLUMN * 0.78;
  for (let sweep = 0; sweep < 8; sweep++) {
    const sequence = sweep % 2 ? [...rows.keys()].reverse() : [...rows.keys()];
    for (const r of sequence) {
      const wish: Record<string, number> = {};
      for (const id of rows[r]) {
        const others = (links[id] ?? []).filter(l => rowOf[l.to] !== r);
        const total = others.reduce((s, l) => s + l.weight, 0);
        wish[id] = total ? others.reduce((s, l) => s + l.weight * x[l.to], 0) / total : x[id];
      }
      rows[r].sort((a, b) => wish[a] - wish[b] || x[a] - x[b]);
      rows[r].forEach((id, i) => { x[id] = i ? Math.max(wish[id], x[rows[r][i - 1]] + gap(rows[r][i - 1], id)) : wish[id]; });
      const shift = mean(rows[r].map(id => wish[id])) - mean(rows[r].map(id => x[id]));
      rows[r].forEach(id => { x[id] += shift; });
    }
  }
  const positions: Record<string, Point> = {};
  for (const id of core) positions[id] = { x: x[id], y: rowOf[id] * ROW };

  // ---- everything that stands BESIDE the rows ----------------------------------------------------------------------------------------------
  const free = (px: number, py: number, clear: number) => !Object.values(positions).some(q => Math.abs(q.x - px) < clear && Math.abs(q.y - py) < 58);
  const beside = (px: number, py: number, outward: number, clear = 120): Point => { let at = px; for (let i = 0; i < 14 && !free(at, py, clear); i++) at += outward * 60; return { x: at, y: py }; };
  const centre = core.length ? mean(core.map(id => x[id])) : 0, height = Math.max(1, row) * ROW;
  // A link that runs through the box of a node it does not belong to reads as a connection to it.
  const clearLink = (a: Point, b: Point) => !Object.entries(positions).some(([id, q]) =>
    !((q.x === a.x && q.y === a.y) || (q.x === b.x && q.y === b.y)) && through(a, b, q, id));
  // ... and a node is not dropped ON a link that is already drawn between two placed nodes.
  const offLinks = (at: Point, id: string) => !wires.some(w => {
    const a = positions[`d:${w.device}`], b = positions[`n:${w.net}`];
    return !!a && !!b && w.role !== 'bulk' && through(a, b, at, id);
  });
  /** The first free place near (px, py) from which every link to `ends` is clear: the place itself, a little above / below it, then further out. */
  const place = (px: number, py: number, outward: number, ends: Point[], as: string, clear = 120): Point => {
    for (let out = 0; out < 8; out++) for (const lift of [0, -0.5, 0.5, -1, 1, -1.5, 1.5, -2, 2]) {
      const at = { x: px + outward * 70 * out, y: py + lift * ROW };
      if (free(at.x, at.y, clear) && ends.every(e => clearLink(at, e)) && offLinks(at, as)) return at;
    }
    return beside(px, py, outward, clear);
  };
  for (const net of control) {
    const driven = gates[net].map(d => positions[`d:${d}`]).filter(Boolean);
    if (!driven.length) { positions[`n:${net}`] = beside(centre, height / 2, 1); continue; }
    const left = mean(driven.map(q => q.x)) <= centre;
    positions[`n:${net}`] = place(left ? Math.min(...driven.map(q => q.x)) - 150 : Math.max(...driven.map(q => q.x)) + 150, mean(driven.map(q => q.y)), left ? -1 : 1, driven, 'n:');
  }
  // Shelves: one row just inside the supply and one just inside ground, for what hangs between a net and that rail
  // (load capacitors, the source of a bias net). They exist only when something will stand on them - known beforehand,
  // because supply and ground must be placed FIRST: what hangs on a shelf then keeps out of the links that run to them.
  const shelved = (d: string) => { const nets = conductsAt[d] ?? []; return nets.filter(n => !rail.has(n)).length === 1 ? nets.find(n => rail.has(n)) : undefined; };
  const candidates = [...hanging, ...sources.filter(d => (conductsAt[d] ?? []).some(n => control.includes(n)))];
  const shelfTop = candidates.some(d => supply.includes(shelved(d) ?? '')), shelfBottom = candidates.some(d => ground.includes(shelved(d) ?? ''));
  const top = -ROW * (shelfTop ? 1.9 : 1), bottom = height + ROW * (shelfBottom ? 1.9 : 1);

  // ---- supply above, ground below: each over / under the middle of what hangs on it ------------------------------------------------------------
  const over = (net: string, py: number) => {
    const hangsOn = wires.filter(w => w.net === net && w.role !== 'bulk').map(w => positions[`d:${w.device}`]).filter(Boolean);
    return beside(hangsOn.length ? mean(hangsOn.map(q => q.x)) : centre, py, 1, 110);
  };
  for (const net of supply) positions[`n:${net}`] = over(net, top);
  for (const net of ground) positions[`n:${net}`] = over(net, bottom);

  const hang = (device: string, outward: number) => {
    const nets = conductsAt[device] ?? [], anchor = nets.filter(n => !rail.has(n)).map(n => positions[`n:${n}`]).filter(Boolean), rails = nets.filter(n => rail.has(n));
    if (!anchor.length) return false;
    const ends = [...anchor, ...rails.map(n => positions[`n:${n}`])];
    if (anchor.length === 1 && rails.length) {
      const shelf = supply.includes(rails[0]) ? -ROW * 0.9 : height + ROW * 0.9;
      positions[`d:${device}`] = place(anchor[0].x + outward * 70, shelf, outward || 1, ends, 'd:', 150);
    } else positions[`d:${device}`] = place(mean(anchor.map(q => q.x)) + (anchor.length > 1 && Math.abs(anchor[0].x - anchor[1].x) < 40 ? 110 : 0), mean(anchor.map(q => q.y)) + (anchor.length > 1 ? 0 : ROW), 1, ends, 'd:', 150);
    return true;
  };
  const margin: string[] = [];
  for (const d of sources) if (!((conductsAt[d] ?? []).some(n => control.includes(n)) && hang(d, 0))) margin.push(d);
  for (const d of hanging) if (!hang(d, 1)) margin.push(d);
  const leftmost = Math.min(...Object.values(positions).map(q => q.x), 0);
  // a source between the rails stands at the side, where its two links to supply and ground cross nothing
  margin.sort((a, b) => level[`d:${a}`] - level[`d:${b}`]).forEach((d, i) => {
    const ends = (conductsAt[d] ?? []).map(n => positions[`n:${n}`]).filter(Boolean);
    positions[`d:${d}`] = place(leftmost - 230 - 170 * i, level[`d:${d}`] * height, -1, ends, 'd:', 150);
  });

  // ---- last: no straight link may run through a node it does not belong to (it would read as a connection) ---------------------------------------
  // The rows are ordered for few crossings, not for this. Of the three nodes involved - the one on the link and the link's two
  // ends - the one with the fewest links steps sideways: a loosely attached net moves, a transistor in its column stays.
  const degree: Record<string, number> = {};
  for (const w of wires) if (w.role !== 'bulk') { degree[`d:${w.device}`] = (degree[`d:${w.device}`] ?? 0) + 1; degree[`n:${w.net}`] = (degree[`n:${w.net}`] ?? 0) + 1; }
  const step = (id: string, away: number) => {
    for (const side of [away, -away]) {
      const at = { x: positions[id].x + side * 72, y: positions[id].y };
      if (!Object.entries(positions).some(([other, o]) => other !== id && Math.abs(o.x - at.x) < 100 && Math.abs(o.y - at.y) < 50)) { positions[id] = at; return true; }
    }
    return false;
  };
  for (let pass = 0; pass < 10; pass++) {
    let moved = false;
    for (const w of wires) {
      const from = `d:${w.device}`, to = `n:${w.net}`, a = positions[from], b = positions[to];
      if (!a || !b || w.role === 'bulk') continue;
      for (const id of Object.keys(positions)) {
        const q = positions[id];
        if (id === from || id === to) continue;
        if (!through(a, b, q, id)) continue;
        const dx = b.x - a.x, dy = b.y - a.y, along = Math.max(0, Math.min(1, ((q.x - a.x) * dx + (q.y - a.y) * dy) / (dx * dx + dy * dy || 1)));
        const nearest = { x: a.x + along * dx, y: a.y + along * dy };
        const loosest = [id, from, to].filter(n => !rail.has(n.slice(2))).sort((m, n) => (degree[m] ?? 0) - (degree[n] ?? 0));
        for (const mover of loosest) if (step(mover, mover === id ? (q.x >= nearest.x ? 1 : -1) : (positions[mover].x >= q.x ? 1 : -1))) { moved = true; break; }
        if (moved) break;
      }
      if (moved) break;
    }
    if (!moved) break;
  }
  return positions;
}
