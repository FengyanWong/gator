// Where the nodes of the circuit graph view stand (record 7.33; the circuit picture places its nodes with it too):
// hintedLayout, fixed rules from what the graph says of the circuit - no agent, no model call.
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

type Point = { x: number; y: number };
/** What the graph says of the circuit, read once (readCircuit): its rails, each device's kind, its wires, and those wires
 *  indexed by device and by net - the conducting terminals, the gates and bases, and the DC current path. */
type Circuit = {
  view: Json; wires: Json[]; supply: string[]; ground: string[]; rail: Set<string>; kind: Record<string, string>;
  conductsAt: Record<string, string[]>; gates: Record<string, string[]>; devicesOn: Record<string, string[]>;
  pathAt: Record<string, string[]>; pathOn: Record<string, string[]>;
};
/** Each node's links to the nodes it is drawn near from left to right, with their weights. */
type Links = Record<string, { to: string; weight: number }[]>;

const ROW = 112, COLUMN = 214, SOURCES = ['vsource', 'isource'];
// A bipolar base is a control terminal like a gate (a run built with a PDK's component list names it).
const conducting = (role: string) => role !== 'gate' && role !== 'base' && role !== 'bulk';
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

/** Where each node stands, by the rules above; null for a graph without a supply and a ground net. Its steps stand below it,
 *  in the order they run: what the graph says, the heights, the rows and their order from left to right, then what stands
 *  beside the rows, and last the moves that keep each link clear of the nodes it does not join. */
export function hintedLayout(view: Json): Record<string, Point> | null {
  const supply: string[] = view.nets.filter((net: Json) => roleOf(net) === 'supply').map((net: Json) => net.id);
  const ground: string[] = view.nets.filter((net: Json) => roleOf(net) === 'ground').map((net: Json) => net.id);
  if (!supply.length || !ground.length) return null;
  const circuit = readCircuit(view, supply, ground);
  const { level, control, sources, hanging } = heightsOf(circuit);
  const { core, rowOf, rows, lastRow } = rowsOf(circuit, level, control, sources, hanging);
  const links = linksOf(circuit, core, control, sources, hanging);
  const order = walkOrder(circuit, core, links);
  const x = sweepRows(order, links, rows, rowOf);
  const positions: Record<string, Point> = {};
  for (const id of core) positions[id] = { x: x[id], y: rowOf[id] * ROW };
  const centre = core.length ? mean(core.map(id => x[id])) : 0, height = Math.max(1, lastRow) * ROW;
  placeControlNets(circuit, positions, control, centre, height);
  const { top, bottom } = topAndBottom(circuit, control, sources, hanging, height);
  placeRails(circuit, positions, centre, top, bottom);
  placeHanging(circuit, positions, control, sources, hanging, level, height);
  untangle(circuit, positions);
  return positions;
}

/** What the graph says of the circuit (Circuit): the rails, each device's kind, and the wires indexed by device and by net. */
function readCircuit(view: Json, supply: string[], ground: string[]): Circuit {
  const rail = new Set([...supply, ...ground]);
  // a PDK kind ("gpdk045:g45cmim") is placed as its family ("capacitor"), which the backend sends along
  const kind: Record<string, string> = Object.fromEntries(view.devices.map((device: Json) => [device.id, device.family ?? device.kind]));
  const wires: Json[] = view.connections;
  const conductsAt: Record<string, string[]> = {}, gates: Record<string, string[]> = {}, devicesOn: Record<string, string[]> = {};
  const pathAt: Record<string, string[]> = {}, pathOn: Record<string, string[]> = {};          // the DC current path: conducting terminals, no capacitors
  for (const wire of wires) {
    if (conducting(wire.role)) {
      (conductsAt[wire.device] ??= []).push(wire.net); (devicesOn[wire.net] ??= []).push(wire.device);
      if (kind[wire.device] !== 'capacitor') { (pathAt[wire.device] ??= []).push(wire.net); (pathOn[wire.net] ??= []).push(wire.device); }
    } else if (wire.role === 'gate' || wire.role === 'base') (gates[wire.net] ??= []).push(wire.device);
  }
  return { view, wires, supply, ground, rail, kind, conductsAt, gates, devicesOn, pathAt, pathOn };
}

/** The heights, 0 = supply and 1 = ground: a net's is its place on the DC current path, a device's the mean of its nets'. Also
 *  what takes no place in the rows: the control nets (they only drive gates), the sources that feed only rails and control
 *  nets, and the capacitors (`hanging`). */
function heightsOf(circuit: Circuit) {
  const { view, supply, ground, rail, kind, conductsAt, gates, devicesOn } = circuit;
  const fromSupply = stepsFrom(supply, circuit), fromGround = stepsFrom(ground, circuit);
  const level: Record<string, number> = {};
  const isControl = (net: string) => !rail.has(net) && !!gates[net]?.length && (fromSupply[net] === undefined || fromGround[net] === undefined)
    && (devicesOn[net] ?? []).every(device => SOURCES.includes(kind[device]));
  for (const net of view.nets) {
    const toSupply = fromSupply[net.id], toGround = fromGround[net.id];
    if (rail.has(net.id) || isControl(net.id)) continue;
    level[`n:${net.id}`] = toSupply !== undefined && toGround !== undefined ? toSupply / (toSupply + toGround)
      : toSupply !== undefined ? toSupply / (toSupply + 2) : toGround !== undefined ? 1 - toGround / (toGround + 2) : 0.5;
  }
  const railLevel = (net: string) => supply.includes(net) ? 0 : 1;
  const control: string[] = view.nets.filter((net: Json) => isControl(net.id)).map((net: Json) => net.id);
  const sources: string[] = view.devices.filter((device: Json) => SOURCES.includes(kind[device.id])
    && (conductsAt[device.id] ?? []).every(net => rail.has(net) || control.includes(net))).map((device: Json) => device.id);
  const hanging: string[] = view.devices.filter((device: Json) => kind[device.id] === 'capacitor').map((device: Json) => device.id);
  for (const device of view.devices) {
    const known = (conductsAt[device.id] ?? []).map(net => rail.has(net) ? railLevel(net) : level[`n:${net}`]).filter(value => value !== undefined);
    level[`d:${device.id}`] = known.length ? mean(known) : 0.5;
  }
  return { level, control, sources, hanging };
}

/** Device steps from a set of rails. A path may END at another rail but never runs through one. */
function stepsFrom(start: string[], circuit: Circuit): Record<string, number> {
  const { rail, pathAt, pathOn } = circuit;
  const found: Record<string, number> = Object.fromEntries(start.map(net => [net, 0])), queue = [...start];
  while (queue.length) {
    const net = queue.shift()!;
    if (rail.has(net) && !start.includes(net)) continue;
    for (const device of pathOn[net] ?? []) for (const other of pathAt[device] ?? [])
      if (found[other] === undefined) { found[other] = found[net] + 1; queue.push(other); }
  }
  return found;
}

/** The rows: heights that are (nearly) equal share a row. Gives what stands in them (`core`: every node but the rails and what
 *  heightsOf sets beside the rows), each one's row, the rows - empty, they fill from left to right - and the last row's number. */
function rowsOf(circuit: Circuit, level: Record<string, number>, control: string[], sources: string[], hanging: string[]) {
  const { view, rail } = circuit;
  const core: string[] = [
    ...view.devices.filter((device: Json) => !sources.includes(device.id) && !hanging.includes(device.id)).map((device: Json) => `d:${device.id}`),
    ...view.nets.filter((net: Json) => !rail.has(net.id) && !control.includes(net.id)).map((net: Json) => `n:${net.id}`)];
  const sorted = [...core].sort((first, second) => level[first] - level[second]);
  const rowOf: Record<string, number> = {};
  let row = -1, rowStart = -1;
  for (const id of sorted) { if (row < 0 || level[id] - rowStart > 0.07) { row++; rowStart = level[id]; } rowOf[id] = row; }
  const rows: string[][] = Array.from({ length: row + 1 }, () => []);
  return { core, rowOf, rows, lastRow: row };
}

/** What draws the nodes of the rows together from left to right: each wire between two of them (a conducting terminal weighs 2,
 *  a gate or a base 1; no bulk tie), and a tie of 6 between two devices that share two or more nets. */
function linksOf(circuit: Circuit, core: string[], control: string[], sources: string[], hanging: string[]): Links {
  const { wires, rail } = circuit;
  const links: Links = {};
  for (const wire of wires) {
    if (rail.has(wire.net) || control.includes(wire.net) || sources.includes(wire.device) || hanging.includes(wire.device) || wire.role === 'bulk') continue;
    const device = `d:${wire.device}`, net = `n:${wire.net}`, weight = conducting(wire.role) ? 2 : 1;
    (links[device] ??= []).push({ to: net, weight }); (links[net] ??= []).push({ to: device, weight });
  }
  // Two devices that share two or more nets belong above each other; a ring has no natural left-to-right order, so they are tied directly.
  const shared: Record<string, Set<string>> = {};
  for (const wire of wires) if (!rail.has(wire.net) && core.includes(`d:${wire.device}`)) (shared[wire.net] ??= new Set()).add(`d:${wire.device}`);
  const together: Record<string, number> = {};
  for (const members of Object.values(shared)) {
    const list = [...members];
    for (let first = 0; first < list.length; first++) for (let second = first + 1; second < list.length; second++) {
      const key = [list[first], list[second]].sort().join('|'); together[key] = (together[key] ?? 0) + 1;
    }
  }
  for (const [key, count] of Object.entries(together)) if (count >= 2) {
    const [device, partner] = key.split('|');
    (links[device] ??= []).push({ to: partner, weight: 6 }); (links[partner] ??= []).push({ to: device, weight: 6 });
  }
  return links;
}

/** A first order from left to right, by walking the graph: along the heaviest links first, from each device on the supply in
 *  turn, then from each node of the rows not reached yet. */
function walkOrder(circuit: Circuit, core: string[], links: Links): string[] {
  const { wires, supply } = circuit;
  const order: string[] = [], seen = new Set<string>();
  const walk = (id: string) => {
    if (seen.has(id)) return;
    seen.add(id); order.push(id);
    for (const link of [...(links[id] ?? [])].sort((first, second) => second.weight - first.weight)) walk(link.to);
  };
  for (const wire of wires) if (supply.includes(wire.net) && core.includes(`d:${wire.device}`)) walk(`d:${wire.device}`);
  for (const id of core) walk(id);
  return order;
}

/** Each node's x: the rows filled in the walk's order, then eight barycentre sweeps (fewer crossings), down the rows and up in
 *  turn - a node wishes to stand at the weighted mean x of its links into other rows, its row takes the order of the wishes
 *  with a gap between neighbours, and the row moves so that its mean is the wishes' mean. */
function sweepRows(order: string[], links: Links, rows: string[][], rowOf: Record<string, number>): Record<string, number> {
  const x: Record<string, number> = {};
  for (const id of order) { rows[rowOf[id]].push(id); x[id] = (rows[rowOf[id]].length - 1) * COLUMN; }
  // Row membership and link weights stay fixed through the sweeps; only their neighbours' x positions change.
  const across = Object.fromEntries(order.map(id => {
    const others = (links[id] ?? []).filter(l => rowOf[l.to] !== rowOf[id]);
    return [id, { others, total: others.reduce((s, l) => s + l.weight, 0) }] as const;
  }));
  const gap = (left: string, right: string) => left[0] === 'd' && right[0] === 'd' ? COLUMN
    : left[0] === 'n' && right[0] === 'n' ? COLUMN * 0.55 : COLUMN * 0.78;
  for (let sweep = 0; sweep < 8; sweep++) {
    const sequence = sweep % 2 ? [...rows.keys()].reverse() : [...rows.keys()];
    for (const r of sequence) {
      const wish: Record<string, number> = {};
      for (const id of rows[r]) {
        const { others, total } = across[id];
        wish[id] = total ? others.reduce((s, l) => s + l.weight * x[l.to], 0) / total : x[id];
      }
      rows[r].sort((first, second) => wish[first] - wish[second] || x[first] - x[second]);
      rows[r].forEach((id, index) => { x[id] = index ? Math.max(wish[id], x[rows[r][index - 1]] + gap(rows[r][index - 1], id)) : wish[id]; });
      const shift = mean(rows[r].map(id => wish[id])) - mean(rows[r].map(id => x[id]));
      rows[r].forEach(id => { x[id] += shift; });
    }
  }
  return x;
}

// ---- what stands BESIDE the rows is placed by these, given where everything placed so far stands -------------------------------
/** Is (px, py) free: nothing placed less than `clear` across and 58 up or down from it? */
const free = (positions: Record<string, Point>, px: number, py: number, clear: number) =>
  !Object.values(positions).some(point => Math.abs(point.x - px) < clear && Math.abs(point.y - py) < 58);
/** The first free place from (px, py) outward, 60 at a time, at most 14 steps out. */
const beside = (positions: Record<string, Point>, px: number, py: number, outward: number, clear = 120): Point => {
  let at = px;
  for (let tries = 0; tries < 14 && !free(positions, at, py, clear); tries++) at += outward * 60;
  return { x: at, y: py };
};
// A link that runs through the box of a node it does not belong to reads as a connection to it.
const clearLink = (positions: Record<string, Point>, start: Point, end: Point) => !Object.entries(positions).some(([id, point]) =>
  !((point.x === start.x && point.y === start.y) || (point.x === end.x && point.y === end.y)) && through(start, end, point, id));
// ... and a node is not dropped ON a link that is already drawn between two placed nodes.
const offLinks = (positions: Record<string, Point>, wires: Json[], at: Point, id: string) => !wires.some(wire => {
  const start = positions[`d:${wire.device}`], end = positions[`n:${wire.net}`];
  return !!start && !!end && wire.role !== 'bulk' && through(start, end, at, id);
});
/** The first free place near (px, py) from which every link to `ends` is clear: the place itself, a little above / below it, then further out. */
const place = (positions: Record<string, Point>, wires: Json[], px: number, py: number, outward: number, ends: Point[], as: string, clear = 120): Point => {
  for (let out = 0; out < 8; out++) for (const lift of [0, -0.5, 0.5, -1, 1, -1.5, 1.5, -2, 2]) {
    const at = { x: px + outward * 70 * out, y: py + lift * ROW };
    if (free(positions, at.x, at.y, clear) && ends.every(end => clearLink(positions, at, end)) && offLinks(positions, wires, at, as)) return at;
  }
  return beside(positions, px, py, outward, clear);
};

/** The control nets stand beside the devices whose gates they drive, on the side of the rows where those stand; one whose
 *  devices are not in the rows stands half way down, in the middle or right of it where there is room. */
function placeControlNets(circuit: Circuit, positions: Record<string, Point>, control: string[], centre: number, height: number) {
  const { wires, gates } = circuit;
  for (const net of control) {
    const driven = gates[net].map(device => positions[`d:${device}`]).filter(Boolean);
    if (!driven.length) { positions[`n:${net}`] = beside(positions, centre, height / 2, 1); continue; }
    const left = mean(driven.map(point => point.x)) <= centre;
    positions[`n:${net}`] = place(positions, wires,
      left ? Math.min(...driven.map(point => point.x)) - 150 : Math.max(...driven.map(point => point.x)) + 150, mean(driven.map(point => point.y)),
      left ? -1 : 1, driven, 'n:');
  }
}

/** Where supply and ground stand: a row above the rows and a row below them, further out where there is a shelf. Shelves: one
 *  row just inside the supply and one just inside ground, for what hangs between a net and that rail (load capacitors, the
 *  source of a bias net). They exist only when something will stand on them - known beforehand, because supply and ground
 *  must be placed FIRST: what hangs on a shelf then keeps out of the links that run to them. */
function topAndBottom(circuit: Circuit, control: string[], sources: string[], hanging: string[], height: number) {
  const { supply, ground, rail, conductsAt } = circuit;
  const shelved = (device: string) => {
    const nets = conductsAt[device] ?? [];
    return nets.filter(net => !rail.has(net)).length === 1 ? nets.find(net => rail.has(net)) : undefined;
  };
  const candidates = [...hanging, ...sources.filter(device => (conductsAt[device] ?? []).some(net => control.includes(net)))];
  const shelfTop = candidates.some(device => supply.includes(shelved(device) ?? '')),
    shelfBottom = candidates.some(device => ground.includes(shelved(device) ?? ''));
  const top = -ROW * (shelfTop ? 1.9 : 1), bottom = height + ROW * (shelfBottom ? 1.9 : 1);
  return { top, bottom };
}

/** Supply above, ground below: each over / under the middle of what hangs on it. */
function placeRails(circuit: Circuit, positions: Record<string, Point>, centre: number, top: number, bottom: number) {
  const { wires, supply, ground } = circuit;
  const over = (net: string, py: number) => {
    const hangsOn = wires.filter(wire => wire.net === net && wire.role !== 'bulk').map(wire => positions[`d:${wire.device}`]).filter(Boolean);
    return beside(positions, hangsOn.length ? mean(hangsOn.map(point => point.x)) : centre, py, 1, 110);
  };
  for (const net of supply) positions[`n:${net}`] = over(net, top);
  for (const net of ground) positions[`n:${net}`] = over(net, bottom);
}

/** What hangs beside the rows - a source that feeds a control net, and each capacitor - stands by the nets it joins: on its
 *  rail's shelf when it joins one net and a rail, else beside its nets. What joins no placed net, or is a source that feeds
 *  none, stands in the margin left of everything, at its own height, the highest nearest. */
function placeHanging(circuit: Circuit, positions: Record<string, Point>, control: string[], sources: string[], hanging: string[],
  level: Record<string, number>, height: number) {
  const { wires, supply, rail, conductsAt } = circuit;
  const hang = (device: string, outward: number) => {
    const nets = conductsAt[device] ?? [], anchor = nets.filter(net => !rail.has(net)).map(net => positions[`n:${net}`]).filter(Boolean),
      rails = nets.filter(net => rail.has(net));
    if (!anchor.length) return false;
    const ends = [...anchor, ...rails.map(net => positions[`n:${net}`])];
    if (anchor.length === 1 && rails.length) {
      const shelf = supply.includes(rails[0]) ? -ROW * 0.9 : height + ROW * 0.9;
      positions[`d:${device}`] = place(positions, wires, anchor[0].x + outward * 70, shelf, outward || 1, ends, 'd:', 150);
    } else positions[`d:${device}`] = place(positions, wires,
      mean(anchor.map(point => point.x)) + (anchor.length > 1 && Math.abs(anchor[0].x - anchor[1].x) < 40 ? 110 : 0),
      mean(anchor.map(point => point.y)) + (anchor.length > 1 ? 0 : ROW), 1, ends, 'd:', 150);
    return true;
  };
  const margin: string[] = [];
  for (const device of sources) if (!((conductsAt[device] ?? []).some(net => control.includes(net)) && hang(device, 0))) margin.push(device);
  for (const device of hanging) if (!hang(device, 1)) margin.push(device);
  const leftmost = Math.min(...Object.values(positions).map(point => point.x), 0);
  // a source between the rails stands at the side, where its two links to supply and ground cross nothing
  margin.sort((first, second) => level[`d:${first}`] - level[`d:${second}`]).forEach((device, index) => {
    const ends = (conductsAt[device] ?? []).map(net => positions[`n:${net}`]).filter(Boolean);
    positions[`d:${device}`] = place(positions, wires, leftmost - 230 - 170 * index, level[`d:${device}`] * height, -1, ends, 'd:', 150);
  });
}

/** Last: no straight link may run through a node it does not belong to (it would read as a connection). The rows are ordered
 *  for few crossings, not for this. Of the three nodes involved - the one on the link and the link's two ends - the one with
 *  the fewest links steps sideways: a loosely attached net moves, a transistor in its column stays. */
function untangle(circuit: Circuit, positions: Record<string, Point>) {
  const { wires, rail } = circuit;
  const degree: Record<string, number> = {};
  for (const wire of wires) if (wire.role !== 'bulk') {
    degree[`d:${wire.device}`] = (degree[`d:${wire.device}`] ?? 0) + 1; degree[`n:${wire.net}`] = (degree[`n:${wire.net}`] ?? 0) + 1;
  }
  // Every node is placed now. Moves replace coordinates, so keep the keys and read each node's current position.
  const placedIds = Object.keys(positions);
  const step = (id: string, away: number) => {
    for (const side of [away, -away]) {
      const at = { x: positions[id].x + side * 72, y: positions[id].y };
      if (!placedIds.some(other => { const o = positions[other]; return other !== id && Math.abs(o.x - at.x) < 100 && Math.abs(o.y - at.y) < 50; })) { positions[id] = at; return true; }
    }
    return false;
  };
  for (let pass = 0; pass < 10; pass++) {
    let moved = false;
    for (const wire of wires) {
      const from = `d:${wire.device}`, to = `n:${wire.net}`, start = positions[from], end = positions[to];
      if (!start || !end || wire.role === 'bulk') continue;
      for (const id of placedIds) {
        const point = positions[id];
        if (id === from || id === to) continue;
        if (!through(start, end, point, id)) continue;
        const dx = end.x - start.x, dy = end.y - start.y,
          along = Math.max(0, Math.min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / (dx * dx + dy * dy || 1)));
        const nearest = { x: start.x + along * dx, y: start.y + along * dy };
        const loosest = [id, from, to].filter(node => !rail.has(node.slice(2))).sort((first, second) => (degree[first] ?? 0) - (degree[second] ?? 0));
        for (const mover of loosest)
          if (step(mover, mover === id ? (point.x >= nearest.x ? 1 : -1) : (positions[mover].x >= point.x ? 1 : -1))) { moved = true; break; }
        if (moved) break;
      }
      if (moved) break;
    }
    if (!moved) break;
  }
}
