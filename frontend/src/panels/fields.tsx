// The right column's form fields and folds (plan-refactoring C4, out of Right.tsx): a number box, a byte size with its
// unit, a tick box, a module of the column folded under its heading, and the fold that draws its content only once opened.
import { ReactNode, useEffect, useRef, useState } from 'react';
import type { Json } from '../api';
import { MODULE_KEY_PREFIX } from '../contract';
import { Typed } from './Typed';
import { keep, readKept } from '../kept';

export function Num({ label, value, onChange, title, nullable, disabled, note, after, placeholder, bounded }: { label: string; value: Json; onChange: (v: Json) => void; title?: string; nullable?: boolean; disabled?: boolean; note?: string; after?: ReactNode; placeholder?: string; bounded?: boolean }) {
  // `Typed` keeps what is being typed while the box has focus ("0." and "3e-" are steps towards 0.005 and 3e-4, not
  // values) and drops it as soon as the value changes from outside (reset button, undo, another encoder), focus or not.
  // `bounded`: a 0-to-1 reward coefficient - a number box that declares the backend's range, drawn without the browser's
  // up/down arrows (record 7.171, user: "remove the toggle for these 0 to 1 value boxes"; styles.css `input.bounded`).
  const box = <Typed className={bounded ? 'numeric bounded' : 'numeric'} value={value} disabled={disabled} placeholder={placeholder ?? (nullable ? 'none' : '')}
    {...(bounded ? { type: 'number', min: 0, max: 1, step: 'any', inputMode: 'decimal' as const,
      'aria-invalid': typeof value !== 'number' || value < 0 || value > 1 } : {})}
    format={v => v === null || v === undefined ? '' : String(v)}
    parse={t => t.trim() === '' ? { value: nullable ? null : 0 } : Number.isFinite(Number(t)) ? { value: Number(t) } : undefined}
    onChange={onChange} />;
  return (
    <label title={title} className={disabled ? 'num disabled' : 'num'}><span>{label}{note && <span className="hint"> - {note}</span>}</span>
      {after ? <span className="with-unit">{box}{after}</span> : box}</label>);
}

// A size that the configuration keeps in whole bytes, typed as a number plus a unit. The saved bytes change only when a
// number is typed; choosing another unit converts the shown number and leaves the size alone (1.5 GiB -> 1536 MiB).
// The shown number is always exact - the shortest decimal that gives the saved bytes back - never a rounded version.
const BYTE_UNITS: [string, number][] = [['bytes', 1], ['KiB', 1024], ['MiB', 1024 ** 2], ['GiB', 1024 ** 3], ['TiB', 1024 ** 4]];
const unitSize = (name: string) => BYTE_UNITS.find(([unit]) => unit === name)?.[1] ?? 1;
// The shortest decimal number that gives back exactly these bytes in that unit; undefined when `places` decimals cannot.
const inUnit = (n: number, size: number, places: number): number | undefined => {
  for (let p = 0; p <= places; p++) { const shown = Number((n / size).toFixed(p)); if (Math.round(shown * size) === n) return shown; }
  return undefined;
};
const bestUnit = (n: Json): string => typeof n !== 'number' ? 'GiB'
  : ([...BYTE_UNITS].reverse().find(([, size]) => n >= size && inUnit(n, size, 3) !== undefined) ?? BYTE_UNITS[0])[0];
// Exact in that unit, with as many decimals as it takes (1395864371 bytes in TiB = 0.00126953125); the full quotient
// only for a size that is not a whole number of bytes, which the schema would refuse anyway.
const showIn = (n: number, size: number): string => String(inUnit(n, size, 15) ?? n / size);

export function ByteSize({ label, value, onChange, title, empty }: { label: string; value: Json; onChange: (v: Json) => void; title?: string; empty: string }) {
  const [unit, setUnit] = useState(() => bestUnit(value));
  const sent = useRef<Json>(value);
  const size = unitSize(unit);
  const toBytes = (t: string, s: number): Json => t.trim() === '' ? null : Math.round(Number(t) * s);
  // A value that did not come from this box (loaded configuration, undo) is shown in the unit that reads best.
  useEffect(() => { if (value !== sent.current) { sent.current = value; if (typeof value === 'number') setUnit(bestUnit(value)); } }, [value]);
  const send = (b: Json) => { sent.current = b; onChange(b); };
  return (
    <label title={`${title ? title + ' ' : ''}${typeof value === 'number' ? `Saved as ${value} bytes.` : `Empty = ${empty}.`}`}><span>{label}</span>
      <span className="with-unit">
        {/* The same box as everywhere else (`Typed`): what is being typed survives, in the unit chosen here. */}
        <Typed className="numeric" value={value} placeholder={empty} format={v => typeof v === 'number' ? showIn(v, size) : ''}
          parse={t => { const b = toBytes(t, size); return b === null || Number.isFinite(b) ? { value: b } : undefined; }} onChange={send} />
        {/* Another unit shows the same size in other words; nothing is saved by it. */}
        <select aria-label={`${label}: unit`} value={unit} onChange={e => setUnit(e.target.value)}>
          {BYTE_UNITS.map(([name]) => <option key={name}>{name}</option>)}</select></span></label>);
}

// A whole module of the right column folded under its own heading (user request 2026-09-21). It starts OPEN; the
// viewer's choice is kept in this browser. It is a <details>, so the content stays mounted while folded: nothing inside
// stops working (the network still follows a chosen model, the output root is still looked at). Folded, the line says the
// module's main values, and whether something inside asks for attention - an error or a warning is never just hidden.
export function Module({ id, title, summary, children, defaultOpen = true }: { id: string; title: string; summary: string; children: ReactNode;
  defaultOpen?: boolean }) {
  const key = `${MODULE_KEY_PREFIX}${id}`;
  // `defaultOpen`: open or folded until this browser keeps a choice (record 7.360: Output settings starts folded, user: "by
  // default make output settings collapsible and collapsed so I can see training tab directly").
  const [open, setOpen] = useState(() => readKept(s => { const kept = s.getItem(key); return kept ? kept !== 'closed' : defaultOpen; }, () => defaultOpen));
  const [inside, setInside] = useState<'error' | 'warn' | null>(null);
  const body = useRef<HTMLDivElement>(null);
  const toggle = (now: boolean) => { setOpen(now); keep(s => s.setItem(key, now ? 'open' : 'closed')); };   // private window: not remembered
  // Watched in the page itself, not per render: parts inside keep their own state (the model list, the graph view) and
  // can show an error without this component rendering again.
  useEffect(() => {
    const node = body.current; if (!node) return;
    const look = () => setInside(node.querySelector('.error') ? 'error' : node.querySelector('.warn') ? 'warn' : null);
    look();
    const observer = new MutationObserver(look);
    observer.observe(node, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);
  return (
    <section className="panel">
      <details className="section module" open={open} onToggle={e => { if (e.target === e.currentTarget) toggle(e.currentTarget.open); }}>
        <summary title={open ? 'Fold this module into one line' : 'Unfold this module'}><h3>{title}</h3>
          {!open && inside && <span className={`module-attention ${inside}`}>{inside === 'error' ? 'error inside' : 'warning inside'}</span>}
          {!open && <span className="hint module-summary" title={summary}>{summary}</span>}</summary>
        <div className="module-body" ref={body}>{children}</div>
      </details>
    </section>);
}

/** One number with its label (record 7.360, the Roadster look's key numbers): the label in grey above, the number in the
 *  label face, words before or after it (a unit, "of 200") in grey beside it; `note`, a line in grey under it, for what the
 *  number is to be read with (branch record SIF-116: an episode start that passed before Training's first passing design). */
export const KeyTile = ({ label, value, before, after, note, title }: { label: string; value: ReactNode; before?: string; after?: string; note?: string; title?: string }) => (
  <span className="key-tile" title={title}><span className="key-tile-label">{label}</span>
    <span className="key-tile-value">{before && <span className="unit">{before} </span>}{value}{after && <span className="unit"> {after}</span>}</span>
    {note && <span className="key-tile-note">{note}</span>}</span>);

export const Check = ({ label, value, onChange, title, disabled }: { label: string; value: boolean; onChange: (v: boolean) => void; title?: string; disabled?: boolean }) => (
  <label className="check" title={title}><input type="checkbox" checked={!!value} disabled={disabled} onChange={e => onChange(e.target.checked)} />{label}</label>);

/** New model's "Saved models, to look at" (record 7.265): folded, and the list - every run's save points, a slow read on the
 *  D: drive - is read only once the fold is opened. Its open state goes with it when a Mode that loads a model replaces it. */
export function LookFold({ summary, children }: { summary: ReactNode; children: () => ReactNode }) {
  const [open, setOpen] = useState(false);
  return <details className="look-models" onToggle={e => setOpen(e.currentTarget.open)}>{summary}{open && children()}</details>;
}
