// The circuit graph view (record 7.33): the dialog that draws a save point's graph as the network sees it - the
// attention on every link, the sizes it proposes - opened from a saved model's Details in the RL model window.
import { Dispatch, MutableRefObject, RefObject, SetStateAction, useEffect, useRef, useState } from 'react';
import { api, Json } from '../api';
import { kindUnit, si } from '../units';
import { short } from '../format';
import { hintedLayout } from './circuitLayout';
import { Newest, useNewest } from '../newest';
import { designName, pointText } from '../lineage';

// The circuit graph view (user decision 2026-09-21: ONE on-screen diagnostic picture; nothing drawn is ever written to
// a run's outputs). The chosen save point is replayed by the backend on a state its own run ARCHIVED
// (/api/runs/model/graph-view: no simulation, nothing written); this component only draws the answer:
// devices and nets as nodes, every connection as a line whose thickness is the attention on it, and on each sized
// device what the policy proposes. cytoscape (MIT) is loaded when the view is opened, never with the page.
// It is a NODE-LINK picture of the graph the network sees - not a schematic (user, 2026-09-21). What the page knows about
// the circuit is used only as HINTS: where the nodes stand (circuitLayout.ts), a node's shape and colour by its kind, and a
// small mark at the device end of a link that enters a gate (dot) or a bulk (bar).
// Attention is normalized per RECEIVING node, so a node with one connection always reads 1.0: such lines are drawn
// thin and dashed. The tables beside the picture carry the same numbers.
const fixed = (v: unknown, digits = 3) => typeof v === 'number' ? v.toFixed(digits) : '-';
const DIRECTIONS: Record<string, string> = { to_device: 'what a device takes from its nets', to_net: 'what a net takes from its devices' };
const KIND_COLOUR: Record<string, string> = { nmos: '#dbeafe', pmos: '#fde2e2', bjt: '#fef3c7', diode: '#fef3c7', resistor: '#e6f4ea',
  capacitor: '#e6f4ea', varactor: '#e6f4ea', inductor: '#e6f4ea', vsource: '#f1e8ff', isource: '#f1e8ff', unknown: '#eef0f3' };
const FAMILY: Record<string, string> = { nmos: 'transistor', pmos: 'transistor', bjt: 'transistor', diode: 'passive', resistor: 'passive',
  capacitor: 'passive', varactor: 'passive', inductor: 'passive', vsource: 'source', isource: 'source' };
// A run built with a PDK's component list sees PDK kinds ("gpdk045:g45n1svt"); the backend adds the family each is drawn
// as (an n-type PDK transistor like an nmos). The node is named by the PDK model; shape and colour follow the family.
const look = (d: Json): string => d.family ?? d.kind;
const shortKind = (kind: string) => kind.includes(':') ? kind.split(':').slice(1).join(':') : kind;
const ROLE_COLOUR: Record<string, string> = { supply: '#fecaca', ground: '#d5d9e0', input: '#bbf7d0', output: '#fde68a', bias: '#e9d5ff',
  clock: '#e9d5ff', normal: '#ffffff' };
const netRole = (net: Json) => (net.roles as string[]).find(r => r !== 'normal') ?? 'normal';

/** The drawing's style. The node fills above are the picture's own key (one colour per kind); the canvas, the
 *  lines and their labels take the page's look (record 7.158), read from the canvas, which may stand in a pop-up window. */
function graphStyle(canvas: HTMLElement): Json {
  const style = getComputedStyle(canvas), v = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
  // The lines and the policy's devices take --accent: red in the Roadster look (the reading line says "red" - branch record SIF-37).
  const muted = v('--muted', '#66707e'), accent = v('--accent', '#1f5fbf'), edge = v('--graph-edge', '#c9ced6');
  return [
    { selector: 'node', style: { label: 'data(label)', 'font-size': 10, 'text-wrap': 'wrap', 'text-valign': 'center', 'text-halign': 'center', color: '#1c2430',
      'background-color': 'data(colour)', 'border-width': 1, 'border-color': '#66707e' } },
    // hints from the circuit: a device's shape says its family (transistor / passive / source), its colour its kind; supply and ground stand out
    { selector: 'node[type = "device"]', style: { shape: 'round-rectangle', width: 'label', height: 'label', padding: '7px' } },
    { selector: 'node[family = "passive"]', style: { shape: 'barrel' } },
    { selector: 'node[family = "source"]', style: { shape: 'cut-rectangle' } },
    { selector: 'node[sized = 1]', style: { 'border-width': 3, 'border-color': accent } },
    { selector: 'node[type = "net"]', style: { shape: 'ellipse', width: 'label', height: 22, padding: '5px', 'font-size': 9 } },
    { selector: 'node[role = "supply"], node[role = "ground"]', style: { 'font-size': 11, 'font-weight': 'bold', 'border-width': 2, 'border-color': '#1c2430',
      height: 26, padding: '9px' } },
    { selector: 'node[focus = 1]', style: { 'background-color': 'mapData(focusWeight, 0, 1, #f0f5ff, #73a9f0)' } },
    { selector: 'node[query = 1]', style: { 'border-color': '#9333ea', 'border-width': 4 } },
    { selector: 'edge', style: { 'curve-style': 'bezier', label: 'data(label)', 'font-size': 8, color: muted, 'text-background-color': v('--canvas', '#fff'),
      'text-background-opacity': 0.85, 'text-background-padding': '1px',
      width: 'mapData(attention, 0, 1, 1, 10)', 'line-color': `mapData(attention, 0, 1, ${edge}, ${accent})` } },
    // a link that enters a device at its gate ends in a dot there, one that enters at the bulk in a bar
    { selector: 'edge[role = "gate"], edge[role = "base"]', style: { 'source-arrow-shape': 'circle', 'source-arrow-color': muted, 'arrow-scale': 0.8 } },
    { selector: 'edge[role = "bulk"]', style: { 'source-arrow-shape': 'tee', 'source-arrow-color': muted, 'arrow-scale': 0.8 } },
    { selector: 'edge[trivial = 1]', style: { width: 1, 'line-style': 'dashed', 'line-color': edge } },
    { selector: 'edge.hidden', style: { display: 'none' } },
    { selector: ':selected', style: { 'border-color': v('--bad', '#b3261e'), 'border-width': 3, 'line-color': v('--bad', '#b3261e') } },
  ];
}

/** The attention of one connection for the chosen layer / head / direction; `trivial` = its receiver has no other connection. */
const attentionOf = (connection: Json, layer: number, head: string, direction: string) => {
  const slot = connection.attention?.[layer - 1];
  if (!slot || slot[direction] === undefined) return { value: null, uniform: null, trivial: false };
  const value = head === 'mean' ? slot[direction] : slot[`${direction}_heads`][Number(head) - 1];
  return { value, uniform: slot[`${direction}_uniform`], trivial: slot[`${direction}_uniform`] === 1 };
};

/** A device, a net or a connection clicked on the drawing, by its id. */
type Picked = { type: string; id: string };

/** The Circuit graph view button and the dialog it opens. Its steps stand below it: its hooks - the dialog's state and refs,
 *  `useNewest` and useGraphDrawing (the drawing's effects, with `fit` and `layout` for its tools) - run in this order at every
 *  draw (React keeps a hook's state by its place in that order); the dialog's parts, graphHeading, graphTools and graphSide,
 *  are plain functions called inline, not components, so the tree React keeps is the one it kept before. */
export function CircuitGraphView({ runDir, checkpointId, label }: { runDir: string; checkpointId: string | null; label?: string }) {
  const [view, setView] = useState<Json>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [wanted, setWanted] = useState('');                      // the evaluation typed into the box; '' = the default one
  const [layer, setLayer] = useState(1);
  const [head, setHead] = useState('mean');
  const [direction, setDirection] = useState('to_device');
  const [scope, setScope] = useState('local');
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState<Picked | null>(null);
  // bulk ties double most links to supply / ground; hidden at first, the network sees them all the same
  const [bulk, setBulk] = useState(false);
  // this graph names no supply / ground net: no hints, the package's own layered layout is used
  const [generic, setGeneric] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const canvas = useRef<HTMLDivElement>(null);
  const graph = useRef<Json>(null);                              // the cytoscape instance
  // The padding of the fit the drawing shows; null once the user panned, zoomed or dragged a node (branch record SIF-143).
  const fitted = useRef<number | null>(null);
  const request = useNewest();

  const load = (evaluation: number | null) => {
    if (!checkpointId) return;
    const mine = request.next();
    setBusy(true); setError(null);
    api.modelGraphView(runDir, checkpointId, evaluation)
      .then(answer => {
        if (!mine()) return;
        setView(answer); setWanted(String(answer.step.evaluation)); setPicked(null); setScope('local'); setQuery('');
        setLayer(chosen => Math.min(chosen, Math.max(1, answer.attention.layers)));
        // A head chosen for a model with more heads does not exist here: every edge was drawn at attention 0.
        setHead(chosen => chosen === 'mean' || Number(chosen) <= (answer.attention.heads ?? 0) ? chosen : 'mean');
      })
      .catch(e => { if (mine()) setError(e.status === 404 && e.message === 'Not Found'
        ? 'the backend that is running is older than this view. Restart it once (the view needs one new route), then open the view again.'
        : e.message); })
      .finally(() => { if (mine()) setBusy(false); });
  };
  const show = () => { setView(null); setWanted(''); dialog.current?.showModal(); load(null); };
  const close = () => { request.drop(); dialog.current?.close(); graph.current?.destroy(); graph.current = null; setView(null); setError(null); };
  const { fit, layout } = useGraphDrawing({ view, canvas, graph, fitted, request, layer, head, direction, scope, query, picked, bulk, setPicked,
    setError, setQuery, setGeneric });

  const attention = view?.attention;
  const dense = view?.node_attention;
  const queryIds: string[] = scope === 'group' ? dense?.groups ?? [] : dense?.nodes ?? [];
  const queryId = queryIds.includes(query) ? query : queryIds[0] ?? '';
  const weights = nodeWeights(view, scope, layer, head, queryId);
  const layerCount = scope === 'local' ? attention?.layers ?? 0 : dense?.[`${scope}_layers`]?.length ?? 0;
  const device = picked?.type === 'device' ? view?.devices.find((candidate: Json) => candidate.id === picked.id) : null;
  const net = picked?.type === 'net' ? view?.nets.find((candidate: Json) => candidate.id === picked.id) : null;
  const connection = picked?.type === 'connection' ? view?.connections.find((candidate: Json) => candidate.id === picked.id) : null;
  const around = (device || net) ? view.connections.filter((link: Json) => device ? link.device === device.id : link.net === net.id) : [];
  const towards = device ? 'to_device' : 'to_net';
  return (<>
    <div className="row"><button className="graph-open" disabled={!checkpointId} onClick={show}
      title="Opens a picture of the circuit as the network sees it: attention on every connection and the sizes this save point proposes, replayed on a state its own run archived. Nothing is simulated and nothing is written.">Circuit graph view</button></div>
    <dialog ref={dialog} className="graph-dialog" onCancel={close}>
      {graphHeading({ view, label, close })}
      {error && <p className="error graph-error">The view could not be built: {error}</p>}
      {busy && !view && <p className="hint">Replaying the saved policy on an archived state...</p>}
      {view && <>
        {graphTools({ view, wanted, setWanted, load, busy, attention, dense, scope, setScope, setQuery, layer, setLayer, layerCount, head, setHead,
          direction, setDirection, queryIds, queryId, bulk, setBulk, layout, graph, fit })}
        <div className="graph-body">
          <div ref={canvas} className="graph-canvas" />
          {graphSide({ view, generic, attention, dense, scope, weights, layer, head, picked, device, net, connection, around, towards })}
        </div></>}
    </dialog></>);
}

/** The drawing: `fit` and `layout` for the tools, and its effects - it goes with the dialog, it is drawn once per answer
 *  (cytoscape is fetched on first use), and another choice changes its lines or which of them show. */
function useGraphDrawing({ view, canvas, graph, fitted, request, layer, head, direction, scope, query, picked, bulk, setPicked, setError, setQuery,
  setGeneric }: {
  view: Json; canvas: RefObject<HTMLDivElement>; graph: MutableRefObject<Json>; fitted: MutableRefObject<number | null>; request: Newest;
  layer: number; head: string; direction: string; scope: string; query: string; picked: Picked | null; bulk: boolean;
  setPicked: Dispatch<SetStateAction<Picked | null>>; setError: Dispatch<SetStateAction<string | null>>;
  setQuery: Dispatch<SetStateAction<string>>; setGeneric: Dispatch<SetStateAction<boolean>> }) {
  const fit = (cy: Json, padding: number) => { fitted.current = padding; cy.fit(undefined, padding); };
  const layout = (name: string, of: Json = view) => {
    const cy = graph.current; if (!cy || !of) return;
    const hinted = name === 'hints' ? hintedLayout(of) : null;
    if (hinted) cy.nodes().forEach((node: Json) => { const at = hinted[node.id()]; if (at) node.position(at); });
    else {
      const roots = cy.nodes('[role = "supply"]');
      cy.layout(name === 'spread' ? { name: 'cose', animate: false, randomize: false, nodeRepulsion: () => 14000, idealEdgeLength: () => 90, padding: 30 }
        : { name: 'breadthfirst', directed: false, roots: roots.length ? roots : cy.nodes('[type = "net"]').first(), spacingFactor: 1.3, padding: 30,
          animate: false }).run();
      if (name !== 'spread') groundDown(cy);
    }
    if (name === 'hints') setGeneric(!hinted);
    fit(cy, 30);
  };

  // The dialog can go away while open (a Mode or model changed in another window): the drawing, its render loop and
  // its window listeners go with it, as Close does.
  useEffect(() => () => { request.drop(); graph.current?.destroy(); graph.current = null; }, []);
  // Draw once per answer. cytoscape is fetched here, on first use.
  useEffect(() => {
    if (!view || !canvas.current) return;
    let cancelled = false;
    import('cytoscape').then(({ default: cytoscape }) => {
      if (cancelled || !canvas.current) return;
      graph.current?.destroy();
      const elements = graphElements(view);
      const cy = cytoscape({ container: canvas.current, elements, minZoom: 0.2, maxZoom: 3, wheelSensitivity: 0.3, style: graphStyle(canvas.current) });
      addListeners(cy, fitted, setPicked);
      graph.current = cy;
      (canvas.current as Json).__cy = cy;                        // the browser check reads the drawn graph through this
      layout('hints', view);
      paint(cy, view, layer, head, direction, scope, query);
      cy.edges('[bulk = 1]').toggleClass('hidden', !bulk);
    }, (e: Error) => {             // the drawing package is fetched on first use: a failed fetch left the picture blank, unexplained
      if (!cancelled) setError(`the drawing package could not be loaded (${e?.message ?? e}). Reload the page, then open the view again.`);
    });
    return () => { cancelled = true; };
  }, [view]);
  // Another layer, head or direction: only the lines change, the picture stays where the user put it.
  useEffect(() => { if (graph.current && view) paint(graph.current, view, layer, head, direction, scope, query); }, [layer, head, direction, scope, query]);
  useEffect(() => {
    if (scope === 'global' && picked && picked.type !== 'connection') setQuery(`${picked.type === 'device' ? 'd' : 'n'}:${picked.id}`);
  }, [picked, scope]);
  useEffect(() => { graph.current?.edges('[bulk = 1]').toggleClass('hidden', !bulk); }, [bulk, view]);
  return { fit, layout };
}

/** What the drawing is made of: a node per device - its kind and, when the policy sizes it, what it proposes - and per net,
 *  with its role; a line per connection, with its terminal and role, at attention 0 until it is painted. */
function graphElements(view: Json) {
  const proposal: Record<string, string[]> = {};
  for (const group of view.groups) if (group.mutable && group.policy_value != null)
    for (const member of group.members) (proposal[member.device] ??= []).push(
      `${member.parameter} ${si(group.value * member.ratio, group.unit)} -> ${si(group.policy_value * member.ratio, group.unit)}`);
  const elements = [
    ...view.devices.map((device: Json) => ({ data: { id: `d:${device.id}`, type: 'device', kind: device.kind, family: FAMILY[look(device)] ?? 'other',
      colour: KIND_COLOUR[look(device)] ?? KIND_COLOUR.unknown, sized: device.groups.length > 0 ? 1 : 0,
      label: [device.id, shortKind(device.kind), ...(proposal[device.id] ?? [])].join('\n') } })),
    ...view.nets.map((net: Json) => ({ data: { id: `n:${net.id}`, type: 'net', role: netRole(net), colour: ROLE_COLOUR[netRole(net)] ?? ROLE_COLOUR.normal,
      label: net.id } })),
    ...view.connections.map((link: Json) => ({ data: { id: `c:${link.id}`, source: `d:${link.device}`, target: `n:${link.net}`, label: link.terminal,
      role: link.role, attention: 0, trivial: 0, bulk: link.role === 'bulk' ? 1 : 0 } })),
  ];
  return elements;
}

/** What the drawing does when it is used: a click on a device, a net or a line picks it, a click beside them picks nothing;
 *  and while it shows a fit, it is fitted to its box again. */
function addListeners(cy: import('cytoscape').Core, fitted: MutableRefObject<number | null>, setPicked: Dispatch<SetStateAction<Picked | null>>) {
  cy.on('tap', 'node, edge', (event: Json) => {
    const id: string = event.target.id();
    setPicked({ type: id[0] === 'd' ? 'device' : id[0] === 'n' ? 'net' : 'connection', id: id.slice(2) });
  });
  cy.on('tap', (event: Json) => { if (event.target === cy) setPicked(null); });
  // Branch record SIF-143: the drawing follows its box (SIF-66) but kept its zoom and pan, so a refusal's line over the
  // tools cut the lowest node, ground, in half. While it shows a fit, a box of another size fits it again; once the user
  // pans, zooms or drags a node the view is theirs, until Fit or a layout button. (cytoscape's resize is debounced: one
  // may come after the drawing was let go.)
  cy.on('dragpan scrollzoom pinchzoom', () => { fitted.current = null; });
  cy.on('dragfree', 'node', () => { fitted.current = null; });
  cy.on('resize', () => { if (fitted.current != null && !cy.destroyed()) cy.fit(undefined, fitted.current); });
}

/** The dialog's heading: its name with the model's label, the save point the view shows, and Close. */
function graphHeading({ view, label, close }: { view: Json; label: string | undefined; close: () => void }) {
  return <div className="row"><h3>Circuit graph view{label ? ` - ${label.replace(/:[0-9a-f]{16}$/, '')}` : ''}</h3><span className="spacer" />
    {/* The save point by its evaluations, as the structure dialog beside it names it; its id on hover (branch record SIF-67). */}
    {view && <span className="hint" title={view.checkpoint_id}>
      {designName(view.network)} {view.network.hidden_dim}/{view.network.heads}/{view.network.layers} - save point {pointText(view.checkpoint_id)}
      {view.origin === 'synthetic' ? ' - MOCK' : ''}</span>}
    <button className="dialog-close" aria-label="Close" title="Close (Esc)" onClick={close}>{'\u00d7'}</button></div>;
}

/** The row of tools over the drawing: the archived evaluation to show (typed, or one earlier or later), the attention to draw
 *  (for an encoder with attention), the bulk ties, the layouts and Fit. */
function graphTools({ view, wanted, setWanted, load, busy, attention, dense, scope, setScope, setQuery, layer, setLayer, layerCount, head, setHead,
  direction, setDirection, queryIds, queryId, bulk, setBulk, layout, graph, fit }: {
  view: Json; wanted: string; setWanted: Dispatch<SetStateAction<string>>; load: (evaluation: number | null) => void; busy: boolean;
  attention: Json; dense: Json; scope: string; setScope: Dispatch<SetStateAction<string>>; setQuery: Dispatch<SetStateAction<string>>;
  layer: number; setLayer: Dispatch<SetStateAction<number>>; layerCount: Json; head: string; setHead: Dispatch<SetStateAction<string>>;
  direction: string; setDirection: Dispatch<SetStateAction<string>>; queryIds: string[]; queryId: string; bulk: boolean;
  setBulk: Dispatch<SetStateAction<boolean>>; layout: (name: string, of?: Json) => void; graph: MutableRefObject<Json>;
  fit: (cy: Json, padding: number) => void }) {
  return <div className="row graph-tools">
    <label className="graph-step" title="Which archived evaluation of this run: the state the network saw BEFORE it. Nothing is simulated again.">
      Evaluation ({view.step.first} - {view.step.last})
      <input className="numeric" value={wanted} onChange={e => setWanted(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && Number(wanted) >= 1) load(Number(wanted)); }} /></label>
    <button disabled={busy || !(Number(wanted) >= 1)} onClick={() => load(Number(wanted))}>Show</button>
    <button disabled={busy || view.step.evaluation <= view.step.first} onClick={() => load(view.step.evaluation - 1)}
      title="One archived evaluation earlier">&lt;</button>
    <button disabled={busy || view.step.evaluation >= view.step.last} onClick={() => load(view.step.evaluation + 1)}
      title="One archived evaluation later">&gt;</button>
    {attention.available && attentionChoices({ attention, dense, scope, setScope, setQuery, layer, setLayer, layerCount, head, setHead, direction,
      setDirection, queryIds, queryId })}
    <label className="check graph-bulk" title="Bulk ties are part of what the network sees, and mostly run beside a source link to supply or ground. Hidden at first to keep the picture readable; the numbers and the tables do not change.">
      <input type="checkbox" checked={bulk} onChange={e => setBulk(e.target.checked)} />Bulk connections</label>
    <span className="spacer" />
    <button onClick={() => layout('hints')} title="Positions from what the graph says about the circuit: supply on top, ground at the bottom, every node at its place on the current path, paired devices above each other. Fixed rules, no agent.">Circuit hints</button>
    <button onClick={() => layout('layers')} title="The drawing package's own layered layout, which knows nothing about circuits">Layered</button>
    <button onClick={() => layout('spread')} title="Let the nodes push each other apart, starting from where they are">Spread out</button>
    <button onClick={() => graph.current && fit(graph.current, 24)} title="Fit the whole graph in the view">Fit</button>
  </div>;
}

/** The attention to draw: the local port edges, or a global or parameter-group attention when the network has one; then its
 *  block or readout, its head, and what the line thickness shows or which node receives. */
function attentionChoices({ attention, dense, scope, setScope, setQuery, layer, setLayer, layerCount, head, setHead, direction, setDirection,
  queryIds, queryId }: {
  attention: Json; dense: Json; scope: string; setScope: Dispatch<SetStateAction<string>>; setQuery: Dispatch<SetStateAction<string>>;
  layer: number; setLayer: Dispatch<SetStateAction<number>>; layerCount: Json; head: string; setHead: Dispatch<SetStateAction<string>>;
  direction: string; setDirection: Dispatch<SetStateAction<string>>; queryIds: string[]; queryId: string }) {
  return <>
    <label>Attention<select className="graph-scope" value={scope} onChange={e => { setScope(e.target.value); setQuery(''); setLayer(1); }}>
      <option value="local">Local port edges</option>
      {!!dense?.global_layers?.length && <option value="global">Global node attention</option>}
      {!!dense?.group_layers?.length && <option value="group">Parameter-group attention</option>}</select></label>
    {/* Named as its options and the tables name it (branch record SIF-62): the label said "Layer" over "block 1". */}
    <label>{scope === 'group' ? 'Readout' : 'Block'}<select className="graph-layer" value={layer} onChange={e => setLayer(Number(e.target.value))}>
      {Array.from({ length: layerCount }, (_, index) => <option key={index} value={index + 1}>{scope === 'group' ? 'readout' : 'block'} {index + 1}</option>)}
    </select></label>
    <label>Head<select className="graph-head" value={head} onChange={e => setHead(e.target.value)}><option value="mean">mean of {attention.heads}</option>
      {Array.from({ length: attention.heads }, (_, index) => <option key={index} value={String(index + 1)}>head {index + 1}</option>)}</select></label>
    {scope === 'local'
      ? <label>Line thickness shows<select className="graph-direction" value={direction} onChange={e => setDirection(e.target.value)}>
        {Object.entries(DIRECTIONS).map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>
      : <label>{scope === 'group' ? 'Parameter group' : 'Receiving node'}<select className="graph-query" value={queryId}
        onChange={e => setQuery(e.target.value)}>
        {queryIds.map(id => <option key={id} value={id}>{id}</option>)}</select></label>}</>;
}

/** Beside the drawing: the state it shows, the notes on the picture and its legend, the sizes now / proposed / tried, what is
 *  selected and what was measured in this state. */
function graphSide({ view, generic, attention, dense, scope, weights, layer, head, picked, device, net, connection, around, towards }: {
  view: Json; generic: boolean; attention: Json; dense: Json; scope: string; weights: number[]; layer: number; head: string;
  picked: Picked | null; device: Json; net: Json; connection: Json; around: Json; towards: 'to_device' | 'to_net' }) {
  return <div className="graph-side">
    {/* saved_at is an evaluation count, not a clock time (branch record SIF-62: it read "written at 20", or "at ?"). */}
    <p className="hint graph-state"><b>Evaluation {view.step.evaluation}</b> of this run (state before it: {view.step.status}){view.step.saved_at != null
      ? `; this save point was written after evaluation ${view.step.saved_at}` : ''}.
      {view.step.evaluation > (view.step.saved_at ?? Infinity) ? ' This state comes after the save point: the model never saw it while training.' : ''}</p>
    {generic && <p className="note graph-generic">This graph names no supply and no ground net, so there are no circuit hints for the positions: the
      drawing package's own layered layout is used.</p>}
    {!attention.available && <p className="note graph-no-attention">{attention.reason}</p>}
    {attention.available && <div className="note graph-reading"><p>{scope === 'local' ? view.reading : dense?.reading}</p>
      <p className="hint">{scope === 'local'
        ? 'Thick red = much attention; thin dashed grey = a receiver with a single connection (always 1.0). Red border = a device whose size the policy sets.'
        : 'Darker node fill = greater weight for the chosen query, scaled to its strongest weight. Purple border = receiving node. Lines show physical connections.'
      }</p></div>}
    {scope !== 'local' && <table className="grid small graph-node-attention"><thead><tr><th>Node</th><th>Attention</th><th>Uniform</th></tr></thead><tbody>
      {(dense?.nodes ?? []).map((id: string, index: number) => <tr key={id}><td>{id}</td><td className="numeric">{fixed(weights[index], 5)}</td>
        <td className="numeric">{fixed(1 / dense.nodes.length, 5)}</td></tr>)}</tbody></table>}
    {view.vocabulary?.name && view.vocabulary.name !== 'standard' && <p className="hint graph-vocabulary">The network of this run knows the
      components of <b>{view.vocabulary.label}</b>: a node shows its PDK model.</p>}
    <p className="hint graph-legend"><b>Nodes:</b> rounded boxes = transistors (blue nmos, red pmos, yellow bipolar), barrels = R / C / L and diodes,
      cut corners = sources, circles = nets
      (red supply, grey ground, green input, yellow output). <b>Links:</b> one ending in a dot enters the device at its gate, one ending in a bar at its bulk.
      Positions follow fixed rules from the circuit (supply on top, ground at the bottom, the current path in between); it is the network's graph, not a
      schematic.</p>
    <h4>Sizes: now, proposed, tried</h4>
    {sizesTable(view)}
    <p className="hint">{view.actions_note} Range of z: -1 = lower bound, +1 = upper bound.</p>
    <h4>Selected</h4>
    {!picked && <p className="hint graph-picked">Click a device, a net or a line. Nodes can be dragged; the wheel zooms.</p>}
    {(device || net) && pickedNode({ device, net, scope, attention, around, layer, head, towards })}
    {connection && pickedConnection({ connection, attention })}
    <h4>Measured in this state</h4>
    <table className="grid small graph-metrics"><tbody>{view.metrics.map((metric: Json) => <tr key={metric.id}><td>{metric.id}</td>
      <td className="numeric">{metric.valid ? si(metric.value, metric.unit) : 'not valid'}</td></tr>)}</tbody></table>
    <p className="hint">On screen only: this picture is never written into the run folder or any export.</p>
  </div>;
}

/** The sizes table: each group's value now, what the policy proposes and what the run tried, each with its action z. */
function sizesTable(view: Json) {
  return <table className="grid small graph-groups"><thead><tr><th>Group</th><th>Now</th><th>Policy proposes</th><th>The run tried</th></tr></thead><tbody>
    {view.groups.map((group: Json) => <tr key={group.id}><td>{group.id}<div className="hint">{group.members.map((member: Json) => member.device).join(', ')}
      {group.mutable ? '' : ' (fixed)'}</div></td>
      <td className="numeric">{si(group.value, group.unit)}</td>
      <td className="numeric">{group.policy_value == null ? '-' : si(group.policy_value, group.unit)}<div className="hint">{group.policy_action == null
        ? '' : `z ${fixed(group.policy_action, 2)}`}</div></td>
      <td className="numeric">{group.recorded_value == null ? '-' : si(group.recorded_value, group.unit)}<div className="hint">{group.recorded_action == null
        ? '' : `z ${fixed(group.recorded_action, 2)}`}</div></td></tr>)}
  </tbody></table>;
}

/** A device or a net that was clicked: what it is, a device's sizes, and in local attention what it takes from each of its
 *  connections. */
function pickedNode({ device, net, scope, attention, around, layer, head, towards }: { device: Json; net: Json; scope: string; attention: Json;
  around: Json; layer: number; head: string; towards: 'to_device' | 'to_net' }) {
  return <div className="graph-picked"><p><b>{(device ?? net).id}</b> - {device ? `${device.kind} (${device.model})` : `net, ${net.roles.join(' / ')}`}</p>
    {/* Sizes as the Sizes table above writes them, "w = 2 um" (branch record SIF-62): short() wrote "w = 2e-6". */}
    {device && <p className="hint">{Object.entries(device.parameters).map(([name, value]) =>
      `${name} = ${typeof value === 'number' && kindUnit(name) ? si(value, kindUnit(name)) : short(value)}`).join(', ') || 'no numeric parameters'}
      {device.groups.length ? ` - sized by ${device.groups.join(', ')}` : ''}</p>}
    {scope === 'local' && attention.available && <table className="grid small graph-around"><thead><tr><th>{device ? 'Terminal' : 'Device'}</th>
      <th>{device ? 'Net' : 'Terminal'}</th><th>Attention</th><th>Uniform</th></tr></thead><tbody>
      {around.map((link: Json) => {
        const linkAttention = attentionOf(link, layer, head, towards);
        return <tr key={link.id}><td>{device ? link.terminal : link.device}</td><td>{device ? link.net : link.terminal}</td>
          <td className="numeric">{fixed(linkAttention.value)}</td><td className="numeric">{fixed(linkAttention.uniform)}</td></tr>;
      })}
    </tbody></table>}
    {scope === 'local' && attention.available && <p className="hint">What <b>{(device ?? net).id}</b> takes from each of its
      connections (block {layer}, {head === 'mean' ? 'mean of the heads' : `head ${head}`}): the column sums to 1.</p>}</div>;
}

/** A line that was clicked: its two ends, and its attention in each block and direction - the mean, each head's and the
 *  uniform one. */
function pickedConnection({ connection, attention }: { connection: Json; attention: Json }) {
  return <div className="graph-picked"><p><b>{connection.device}.{connection.terminal}</b> - <b>{connection.net}</b></p>
    {attention.available ? <table className="grid small graph-around"><thead><tr><th>Block</th><th>Direction</th><th>Mean</th><th>Per head</th>
      <th>Uniform</th></tr></thead><tbody>
      {connection.attention.flatMap((slot: Json) => Object.keys(DIRECTIONS).filter(direction => slot[direction] !== undefined).map(direction =>
        <tr key={`${slot.layer}${direction}`}><td>{slot.layer}</td>
          <td>{direction === 'to_device' ? `${connection.device} takes from ${connection.net}` : `${connection.net} takes from ${connection.device}`}</td>
          <td className="numeric">{fixed(slot[direction])}</td>
          <td className="numeric">{slot[`${direction}_heads`].map((weight: number) => fixed(weight, 2)).join(' ')}</td>
          <td className="numeric">{fixed(slot[`${direction}_uniform`])}</td></tr>))}
    </tbody></table> : <p className="hint">No attention in this encoder.</p>}</div>;
}

/** As in a schematic: ground goes below everything else (a breadth-first walk from the supply meets it early). */
function groundDown(cy: Json) {
  const grounds = cy.nodes('[role = "ground"]');
  const others = cy.nodes().difference(grounds);
  if (!grounds.length || !others.length) return;
  const bottom = Math.max(...others.map((n: Json) => n.position('y')));
  grounds.forEach((g: Json, i: number) => { const xs: number[] = g.neighborhood('node').map((n: Json) => n.position('x'));
    g.position({ x: xs.reduce((a, b) => a + b, 0) / Math.max(1, xs.length) + 60 * i, y: bottom + 130 }); });
}

function nodeWeights(view: Json, scope: string, layer: number, head: string, query: string): number[] {
  const dense = view?.node_attention;
  if (!dense || scope === 'local') return [];
  const queries: string[] = scope === 'group' ? dense.groups : dense.nodes;
  const index = Math.max(0, queries.indexOf(query));
  const heads: number[][][] = dense[`${scope}_layers`]?.[layer - 1] ?? [];
  if (!heads.length) return [];
  return head === 'mean' ? dense.nodes.map((_: string, i: number) => heads.reduce((sum, h) => sum + h[index][i], 0) / heads.length)
    : heads[Number(head) - 1]?.[index] ?? [];
}

function paint(cy: Json, view: Json, layer: number, head: string, direction: string, scope: string, query: string) {
  const weights = nodeWeights(view, scope, layer, head, query);
  const peak = Math.max(...weights, 1e-12);
  const queryId = query || view.node_attention?.nodes?.[0];
  // Nodes and edges change together: flush their style notifications once, including the per-node attention colors.
  cy.batch(() => {
    cy.nodes().data({ focus: 0, query: 0 });
    (view.node_attention?.nodes ?? []).forEach((id: string, i: number) => cy.getElementById(id).data({
      focus: scope !== 'local' ? 1 : 0, focusWeight: (weights[i] ?? 0) / peak, query: scope === 'global' && id === queryId ? 1 : 0,
    }));
    view.connections.forEach((c: Json) => {
      const a = attentionOf(c, scope === 'local' ? layer : 0, head, direction);
      cy.getElementById(`c:${c.id}`).data({ attention: a.value ?? 0, trivial: a.trivial ? 1 : 0 });      // no attention at all: thin solid lines
    });
  });
}
