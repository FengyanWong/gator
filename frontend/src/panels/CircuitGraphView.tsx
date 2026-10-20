import { useEffect, useRef, useState } from 'react';
import { api, Json } from '../api';
import { si } from '../units';
import { short } from '../format';
import { hintedLayout } from './circuitLayout';
import { useNewest } from '../newest';

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
const KIND_COLOUR: Record<string, string> = { nmos: '#dbeafe', pmos: '#fde2e2', bjt: '#fef3c7', diode: '#fef3c7', resistor: '#e6f4ea', capacitor: '#e6f4ea', varactor: '#e6f4ea', inductor: '#e6f4ea', vsource: '#f1e8ff', isource: '#f1e8ff', unknown: '#eef0f3' };
const FAMILY: Record<string, string> = { nmos: 'transistor', pmos: 'transistor', bjt: 'transistor', diode: 'passive', resistor: 'passive', capacitor: 'passive', varactor: 'passive', inductor: 'passive', vsource: 'source', isource: 'source' };
// A run built with a PDK's component list sees PDK kinds ("gpdk045:g45n1svt"); the backend adds the family each is drawn
// as (an n-type PDK transistor like an nmos). The node is named by the PDK model; shape and colour follow the family.
const look = (d: Json): string => d.family ?? d.kind;
const shortKind = (kind: string) => kind.includes(':') ? kind.split(':').slice(1).join(':') : kind;
const ROLE_COLOUR: Record<string, string> = { supply: '#fecaca', ground: '#d5d9e0', input: '#bbf7d0', output: '#fde68a', bias: '#e9d5ff', clock: '#e9d5ff', normal: '#ffffff' };
const netRole = (net: Json) => (net.roles as string[]).find(r => r !== 'normal') ?? 'normal';

/** The drawing's style. The node fills above are the picture's own key (one colour per kind); the canvas, the
 *  lines and their labels take the page's look (record 7.158), read from the canvas, which may stand in a pop-up window. */
function graphStyle(canvas: HTMLElement): Json {
  const style = getComputedStyle(canvas), v = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
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
    { selector: 'node[role = "supply"], node[role = "ground"]', style: { 'font-size': 11, 'font-weight': 'bold', 'border-width': 2, 'border-color': '#1c2430', height: 26, padding: '9px' } },
    { selector: 'node[focus = 1]', style: { 'background-color': 'mapData(focusWeight, 0, 1, #f0f5ff, #73a9f0)' } },
    { selector: 'node[query = 1]', style: { 'border-color': '#9333ea', 'border-width': 4 } },
    { selector: 'edge', style: { 'curve-style': 'bezier', label: 'data(label)', 'font-size': 8, color: muted, 'text-background-color': v('--canvas', '#fff'), 'text-background-opacity': 0.85, 'text-background-padding': '1px',
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
  const [picked, setPicked] = useState<{ type: string; id: string } | null>(null);
  const [bulk, setBulk] = useState(false);                         // bulk ties double most links to supply / ground; hidden at first, the network sees them all the same
  const [generic, setGeneric] = useState(false);                   // this graph names no supply / ground net: no hints, the package's own layered layout is used
  const dialog = useRef<HTMLDialogElement>(null);
  const canvas = useRef<HTMLDivElement>(null);
  const graph = useRef<Json>(null);                              // the cytoscape instance
  const request = useNewest();

  const load = (evaluation: number | null) => {
    if (!checkpointId) return;
    const mine = request.next();
    setBusy(true); setError(null);
    api.modelGraphView(runDir, checkpointId, evaluation)
      .then(v => { if (!mine()) return; setView(v); setWanted(String(v.step.evaluation)); setPicked(null); setScope('local'); setQuery(''); setLayer(l => Math.min(l, Math.max(1, v.attention.layers)));
        // A head chosen for a model with more heads does not exist here: every edge was drawn at attention 0.
        setHead(h => h === 'mean' || Number(h) <= (v.attention.heads ?? 0) ? h : 'mean'); })
      .catch(e => { if (mine()) setError(e.status === 404 && e.message === 'Not Found'
        ? 'the backend that is running is older than this view. Restart it once (the view needs one new route), then open the view again.' : e.message); })
      .finally(() => { if (mine()) setBusy(false); });
  };
  const show = () => { setView(null); setWanted(''); dialog.current?.showModal(); load(null); };
  const close = () => { request.drop(); dialog.current?.close(); graph.current?.destroy(); graph.current = null; setView(null); setError(null); };
  const layout = (name: string, of: Json = view) => {
    const cy = graph.current; if (!cy || !of) return;
    const hinted = name === 'hints' ? hintedLayout(of) : null;
    if (hinted) cy.nodes().forEach((n: Json) => { const at = hinted[n.id()]; if (at) n.position(at); });
    else {
      const roots = cy.nodes('[role = "supply"]');
      cy.layout(name === 'spread' ? { name: 'cose', animate: false, randomize: false, nodeRepulsion: () => 14000, idealEdgeLength: () => 90, padding: 30 }
        : { name: 'breadthfirst', directed: false, roots: roots.length ? roots : cy.nodes('[type = "net"]').first(), spacingFactor: 1.3, padding: 30, animate: false }).run();
      if (name !== 'spread') groundDown(cy);
    }
    if (name === 'hints') setGeneric(!hinted);
    cy.fit(undefined, 30);
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
      const proposal: Record<string, string[]> = {};
      for (const g of view.groups) if (g.mutable && g.policy_value != null)
        for (const m of g.members) (proposal[m.device] ??= []).push(`${m.parameter} ${si(g.value * m.ratio, g.unit)} -> ${si(g.policy_value * m.ratio, g.unit)}`);
      const elements = [
        ...view.devices.map((d: Json) => ({ data: { id: `d:${d.id}`, type: 'device', kind: d.kind, family: FAMILY[look(d)] ?? 'other', colour: KIND_COLOUR[look(d)] ?? KIND_COLOUR.unknown,
          sized: d.groups.length > 0 ? 1 : 0, label: [d.id, shortKind(d.kind), ...(proposal[d.id] ?? [])].join('\n') } })),
        ...view.nets.map((n: Json) => ({ data: { id: `n:${n.id}`, type: 'net', role: netRole(n), colour: ROLE_COLOUR[netRole(n)] ?? ROLE_COLOUR.normal, label: n.id } })),
        ...view.connections.map((c: Json) => ({ data: { id: `c:${c.id}`, source: `d:${c.device}`, target: `n:${c.net}`, label: c.terminal, role: c.role, attention: 0, trivial: 0,
          bulk: c.role === 'bulk' ? 1 : 0 } })),
      ];
      const cy = cytoscape({ container: canvas.current, elements, minZoom: 0.2, maxZoom: 3, wheelSensitivity: 0.3, style: graphStyle(canvas.current) });
      cy.on('tap', 'node, edge', (event: Json) => { const id: string = event.target.id(); setPicked({ type: id[0] === 'd' ? 'device' : id[0] === 'n' ? 'net' : 'connection', id: id.slice(2) }); });
      cy.on('tap', (event: Json) => { if (event.target === cy) setPicked(null); });
      graph.current = cy;
      (canvas.current as Json).__cy = cy;                        // the browser check reads the drawn graph through this
      layout('hints', view);
      paint(cy, view, layer, head, direction, scope, query);
      cy.edges('[bulk = 1]').toggleClass('hidden', !bulk);
    }, (e: any) => {               // the drawing package is fetched on first use: a failed fetch left the picture blank, unexplained
      if (!cancelled) setError(`the drawing package could not be loaded (${e?.message ?? e}). Reload the page, then open the view again.`);
    });
    return () => { cancelled = true; };
  }, [view]);
  // Another layer, head or direction: only the lines change, the picture stays where the user put it.
  useEffect(() => { if (graph.current && view) paint(graph.current, view, layer, head, direction, scope, query); }, [layer, head, direction, scope, query]);
  useEffect(() => { if (scope === 'global' && picked && picked.type !== 'connection') setQuery(`${picked.type === 'device' ? 'd' : 'n'}:${picked.id}`); }, [picked, scope]);
  useEffect(() => { graph.current?.edges('[bulk = 1]').toggleClass('hidden', !bulk); }, [bulk, view]);

  const attention = view?.attention;
  const dense = view?.node_attention;
  const queryIds: string[] = scope === 'group' ? dense?.groups ?? [] : dense?.nodes ?? [];
  const queryId = queryIds.includes(query) ? query : queryIds[0] ?? '';
  const weights = nodeWeights(view, scope, layer, head, queryId);
  const layerCount = scope === 'local' ? attention?.layers ?? 0 : dense?.[`${scope}_layers`]?.length ?? 0;
  const device = picked?.type === 'device' ? view?.devices.find((d: Json) => d.id === picked.id) : null;
  const net = picked?.type === 'net' ? view?.nets.find((n: Json) => n.id === picked.id) : null;
  const connection = picked?.type === 'connection' ? view?.connections.find((c: Json) => c.id === picked.id) : null;
  const around = (device || net) ? view.connections.filter((c: Json) => device ? c.device === device.id : c.net === net.id) : [];
  const towards = device ? 'to_device' : 'to_net';
  return (<>
    <div className="row"><button className="graph-open" disabled={!checkpointId} onClick={show}
      title="Opens a picture of the circuit as the network sees it: attention on every connection and the sizes this save point proposes, replayed on a state its own run archived. Nothing is simulated and nothing is written.">Circuit graph view</button></div>
    <dialog ref={dialog} className="graph-dialog" onCancel={close}>
      <div className="row"><h3>Circuit graph view{label ? ` - ${label.replace(/:[0-9a-f]{16}$/, '')}` : ''}</h3><span className="spacer" />
        {view && <span className="hint">{view.network.encoder_type} {view.network.hidden_dim}/{view.network.heads}/{view.network.layers} - save point {view.checkpoint_id}{view.origin === 'synthetic' ? ' - MOCK' : ''}</span>}
        <button className="dialog-close" aria-label="Close" title="Close (Esc)" onClick={close}>{'\u00d7'}</button></div>
      {error && <p className="error graph-error">The view could not be built: {error}</p>}
      {busy && !view && <p className="hint">Replaying the saved policy on an archived state...</p>}
      {view && <>
        <div className="row graph-tools">
          <label className="graph-step" title="Which archived evaluation of this run: the state the network saw BEFORE it. Nothing is simulated again.">Evaluation ({view.step.first} - {view.step.last})
            <input className="numeric" value={wanted} onChange={e => setWanted(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && Number(wanted) >= 1) load(Number(wanted)); }} /></label>
          <button disabled={busy || !(Number(wanted) >= 1)} onClick={() => load(Number(wanted))}>Show</button>
          <button disabled={busy || view.step.evaluation <= view.step.first} onClick={() => load(view.step.evaluation - 1)} title="One archived evaluation earlier">&lt;</button>
          <button disabled={busy || view.step.evaluation >= view.step.last} onClick={() => load(view.step.evaluation + 1)} title="One archived evaluation later">&gt;</button>
          {attention.available && <>
            <label>Attention<select className="graph-scope" value={scope} onChange={e => { setScope(e.target.value); setQuery(''); setLayer(1); }}>
              <option value="local">Local port edges</option>
              {!!dense?.global_layers?.length && <option value="global">Global node attention</option>}
              {!!dense?.group_layers?.length && <option value="group">Parameter-group attention</option>}</select></label>
            <label>Layer<select className="graph-layer" value={layer} onChange={e => setLayer(Number(e.target.value))}>{Array.from({ length: layerCount }, (_, i) => <option key={i} value={i + 1}>{scope === 'group' ? 'readout' : 'block'} {i + 1}</option>)}</select></label>
            <label>Head<select className="graph-head" value={head} onChange={e => setHead(e.target.value)}><option value="mean">mean of {attention.heads}</option>{Array.from({ length: attention.heads }, (_, i) => <option key={i} value={String(i + 1)}>head {i + 1}</option>)}</select></label>
            {scope === 'local' ? <label>Line thickness shows<select className="graph-direction" value={direction} onChange={e => setDirection(e.target.value)}>{Object.entries(DIRECTIONS).map(([k, text]) => <option key={k} value={k}>{text}</option>)}</select></label>
              : <label>{scope === 'group' ? 'Parameter group' : 'Receiving node'}<select className="graph-query" value={queryId} onChange={e => setQuery(e.target.value)}>
                {queryIds.map(id => <option key={id} value={id}>{id}</option>)}</select></label>}</>}
          <label className="check graph-bulk" title="Bulk ties are part of what the network sees, and mostly run beside a source link to supply or ground. Hidden at first to keep the picture readable; the numbers and the tables do not change."><input type="checkbox" checked={bulk} onChange={e => setBulk(e.target.checked)} />Bulk connections</label>
          <span className="spacer" />
          <button onClick={() => layout('hints')} title="Positions from what the graph says about the circuit: supply on top, ground at the bottom, every node at its place on the current path, paired devices above each other. Fixed rules, no agent.">Circuit hints</button>
          <button onClick={() => layout('layers')} title="The drawing package's own layered layout, which knows nothing about circuits">Layered</button>
          <button onClick={() => layout('spread')} title="Let the nodes push each other apart, starting from where they are">Spread out</button>
          <button onClick={() => graph.current?.fit(undefined, 24)}>Fit</button>
        </div>
        <div className="graph-body">
          <div ref={canvas} className="graph-canvas" />
          <div className="graph-side">
            <p className="hint graph-state"><b>Evaluation {view.step.evaluation}</b> of this run (state before it: {view.step.status}); this save point was written at {view.step.saved_at ?? '?'}.
              {view.step.evaluation > (view.step.saved_at ?? Infinity) ? ' This state is LATER than the save point: the model never saw it while training.' : ''}</p>
            {generic && <p className="note graph-generic">This graph names no supply and no ground net, so there are no circuit hints for the positions: the drawing package's own layered layout is used.</p>}
            {!attention.available && <p className="note graph-no-attention">{attention.reason}</p>}
            {attention.available && <div className="note graph-reading"><p>{scope === 'local' ? view.reading : dense?.reading}</p>
              <p className="hint">{scope === 'local' ? 'Thick blue = much attention; thin dashed grey = a receiver with a single connection (always 1.0). Blue border = a device whose size the policy sets.'
                : 'Darker node fill = greater weight for the chosen query, scaled to its strongest weight. Purple border = receiving node. Lines show physical connections.'}</p></div>}
            {scope !== 'local' && <table className="grid small graph-node-attention"><thead><tr><th>Node</th><th>Attention</th><th>Uniform</th></tr></thead><tbody>
              {(dense?.nodes ?? []).map((id: string, i: number) => <tr key={id}><td>{id}</td><td className="numeric">{fixed(weights[i], 5)}</td>
                <td className="numeric">{fixed(1 / dense.nodes.length, 5)}</td></tr>)}</tbody></table>}
            {view.vocabulary?.name && view.vocabulary.name !== 'standard' && <p className="hint graph-vocabulary">The network of this run knows the components of <b>{view.vocabulary.label}</b>: a node shows its PDK model.</p>}
            <p className="hint graph-legend"><b>Nodes:</b> rounded boxes = transistors (blue nmos, red pmos, yellow bipolar), barrels = R / C / L and diodes, cut corners = sources, circles = nets
              (red supply, grey ground, green input, yellow output). <b>Links:</b> one ending in a dot enters the device at its gate, one ending in a bar at its bulk.
              Positions follow fixed rules from the circuit (supply on top, ground at the bottom, the current path in between); it is the network's graph, not a schematic.</p>
            <h4>Sizes: now, proposed, tried</h4>
            <table className="grid small graph-groups"><thead><tr><th>Group</th><th>Now</th><th>Policy proposes</th><th>The run tried</th></tr></thead><tbody>
              {view.groups.map((g: Json) => <tr key={g.id}><td>{g.id}<div className="hint">{g.members.map((m: Json) => m.device).join(', ')}{g.mutable ? '' : ' (fixed)'}</div></td>
                <td className="numeric">{si(g.value, g.unit)}</td><td className="numeric">{g.policy_value == null ? '-' : si(g.policy_value, g.unit)}<div className="hint">{g.policy_action == null ? '' : `z ${fixed(g.policy_action, 2)}`}</div></td>
                <td className="numeric">{g.recorded_value == null ? '-' : si(g.recorded_value, g.unit)}<div className="hint">{g.recorded_action == null ? '' : `z ${fixed(g.recorded_action, 2)}`}</div></td></tr>)}
            </tbody></table>
            <p className="hint">{view.actions_note} Range of z: -1 = lower bound, +1 = upper bound.</p>
            <h4>Selected</h4>
            {!picked && <p className="hint graph-picked">Click a device, a net or a line. Nodes can be dragged; the wheel zooms.</p>}
            {(device || net) && <div className="graph-picked"><p><b>{(device ?? net).id}</b> - {device ? `${device.kind} (${device.model})` : `net, ${net.roles.join(' / ')}`}</p>
              {device && <p className="hint">{Object.entries(device.parameters).map(([k, v]) => `${k} = ${short(v)}`).join(', ') || 'no numeric parameters'}{device.groups.length ? ` - sized by ${device.groups.join(', ')}` : ''}</p>}
              {scope === 'local' && attention.available && <table className="grid small graph-around"><thead><tr><th>{device ? 'Terminal' : 'Device'}</th><th>{device ? 'Net' : 'Terminal'}</th><th>Attention</th><th>Uniform</th></tr></thead><tbody>
                {around.map((c: Json) => { const a = attentionOf(c, layer, head, towards); return <tr key={c.id}><td>{device ? c.terminal : c.device}</td><td>{device ? c.net : c.terminal}</td>
                  <td className="numeric">{fixed(a.value)}</td><td className="numeric">{fixed(a.uniform)}</td></tr>; })}
              </tbody></table>}
              {scope === 'local' && attention.available && <p className="hint">What <b>{(device ?? net).id}</b> takes from each of its connections (block {layer}, {head === 'mean' ? 'mean of the heads' : `head ${head}`}): the column sums to 1.</p>}</div>}
            {connection && <div className="graph-picked"><p><b>{connection.device}.{connection.terminal}</b> - <b>{connection.net}</b></p>
              {attention.available ? <table className="grid small graph-around"><thead><tr><th>Block</th><th>Direction</th><th>Mean</th><th>Per head</th><th>Uniform</th></tr></thead><tbody>
                {connection.attention.flatMap((slot: Json) => Object.keys(DIRECTIONS).filter(k => slot[k] !== undefined).map(k => <tr key={`${slot.layer}${k}`}><td>{slot.layer}</td>
                  <td>{k === 'to_device' ? `${connection.device} takes from ${connection.net}` : `${connection.net} takes from ${connection.device}`}</td>
                  <td className="numeric">{fixed(slot[k])}</td><td className="numeric">{slot[`${k}_heads`].map((h: number) => fixed(h, 2)).join(' ')}</td><td className="numeric">{fixed(slot[`${k}_uniform`])}</td></tr>))}
              </tbody></table> : <p className="hint">No attention in this encoder.</p>}</div>}
            <h4>Measured in this state</h4>
            <table className="grid small graph-metrics"><tbody>{view.metrics.map((m: Json) => <tr key={m.id}><td>{m.id}</td><td className="numeric">{m.valid ? si(m.value, m.unit) : 'not valid'}</td></tr>)}</tbody></table>
            <p className="hint">On screen only: this picture is never written into the run folder or any export.</p>
          </div>
        </div></>}
    </dialog></>);
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
