import type { Json } from './api';

/** One way of writing a quantity in the whole page (record 7.208, user: "a unified way of unit representation in the parameters
 *  probes and specs windows considering the convenience usage of users", chose "Prefix per value"): the number, an SI prefix and
 *  the unit, as Virtuoso's forms write them - 1.2 um, 45 nm, 9.535 kohm, 400 uA, 100 MHz, -30 dB, 60 deg - in English letters
 *  only (user: "dont use greek characters for unit, use english letters instead"; the Greek spellings µm, kΩ, ° are still
 *  read). The digits are the stored number's own, moved and never computed, so what is shown is exactly what is stored.
 *  Typed, any form is read - 400u, 400 uA, 0.4mA, 4e-4 - into the unit its row stores; a plain number is in that unit, the one
 *  the Unit column shows; a wrong
 *  quantity is refused in words. Stored numbers and units never change by being shown. The table is the backend's
 *  (units.py `written_forms`, sent with /api/schema), and units.py `text` writes the backend's messages the same way. */

type Rule = [string, number, number];                 // canonical unit, factor to it, offset
let spellings: Record<string, Rule> = {};
let prefixable = new Set<string>();
let symbols: Record<string, string> = {};
let quantities: Record<string, string> = {};
let kinds: Record<string, string> = {};

/** Takes the table the backend sends with /api/schema. */
export function setUnitForms(forms: Json) {
  if (!forms) return;
  spellings = forms.spellings ?? {};
  prefixable = new Set(forms.prefixable ?? []);
  symbols = forms.symbols ?? {};
  quantities = forms.quantities ?? {};
  kinds = forms.kinds ?? {};
}

/** The unit a parameter of this name is sized in (w and l: m, m and nf: count, r: ohm, c: F), when its kind says it. */
export const kindUnit = (parameter: string | null | undefined): string | null => kinds[parameter ?? ''] ?? null;

/** Whether two units measure the same quantity (um and m, uA and A): a value of one can be written in the other. */
export const sameQuantity = (a: string | null | undefined, b: string | null | undefined) => {
  const x = spellings[a ?? ''], y = spellings[b ?? ''];
  return !!x && !!y && x[0] === y[0];
};

const PREFIX: Record<number, string> = { [-18]: 'a', [-15]: 'f', [-12]: 'p', [-9]: 'n', [-6]: 'u', [-3]: 'm', 0: '', 3: 'k', 6: 'M', 9: 'G', 12: 'T' };
const LETTER: Record<string, number> = { a: -18, f: -15, p: -12, n: -9, u: -6, 'µ': -6, 'μ': -6, m: -3, k: 3, K: 3, M: 6, G: 9, T: 12 };
/** The SI prefix letters of typed numbers and their powers of ten (plan-refactoring C8: the editors' typed numbers read them from
 *  here - editorRules.ts readNumber, whose letters f p n u µ μ m k K M G T all have these powers). */
export { LETTER as PREFIX_POWERS };
/** Maestro's unit prefixes as factors, for telling a unit from its base (WorkingCopy.tsx prefixFactor). Not LETTER's set: the
 *  micro sign µ only (no Greek μ) and no K - so a unit written that way is not taken for a multiple of its base. */
export const PREFIX_FACTOR: Record<string, number> = { T: 1e12, G: 1e9, M: 1e6, k: 1e3, m: 1e-3, u: 1e-6, 'µ': 1e-6, n: 1e-9, p: 1e-12, f: 1e-15, a: 1e-18 };

/** How a unit is written next to a number, in English letters: Ω as ohm, ° as deg; a plain number or a count without one. */
export const unitSymbol = (unit: string | null | undefined) => { const u = unit ?? ''; return u in symbols ? symbols[u] : english(u); };

/** A unit's spelling in English letters: µm as um, kΩ as kohm, ° as deg. */
const english = (unit: string) => unit.replace(/^[µμ]/, 'u').replace(/Ω/g, 'ohm').replace(/°C/g, 'degC').replace(/°/g, 'deg');

/** What the Unit column shows for a row: the unit its numbers are stored in - and a plain number typed in the row means -
 *  in English letters (um, kohm, deg); a count or a plain number by name. */
export function unitLabel(unit: string | null | undefined): string {
  const u = unit ?? '';
  return u in symbols ? symbols[u] || u : english(u);
}

/** Whether the page knows a unit (µm, kΩ and ° are read as spellings of their own). */
export const knownUnit = (unit: string) => unit in spellings;

/** Whether two units are the same unit, spelled differently (um and µm, deg and degree): nothing to convert. */
export const sameUnit = (a: string | null | undefined, b: string | null | undefined) => {
  const x = spellings[a ?? ''], y = spellings[b ?? ''];
  return (a ?? '') === (b ?? '') || (!!x && !!y && x[0] === y[0] && x[1] === y[1] && x[2] === y[2]);
};

/** A stored number of a row moved from one unit to another of the same quantity, exactly (0.6 um is 600 nm): the digits are
 *  moved, never computed. null: the units are not the same quantity, or not a power of ten apart. */
export function convert(value: unknown, from: string | null | undefined, to: string | null | undefined): number | null {
  const x = spellings[from ?? ''], y = spellings[to ?? ''];
  if (typeof value !== 'number' || !Number.isFinite(value) || !x || !y || x[0] !== y[0] || x[2] !== 0 || y[2] !== 0) return null;
  const tens = Math.round(Math.log10(x[1] / y[1]));
  if (Math.abs(10 ** tens - x[1] / y[1]) > 1e-12 * (x[1] / y[1])) return null;
  if (value === 0 || tens === 0) return value;
  const { digits, exponent } = decimal(value);
  return Number(`${value < 0 ? '-' : ''}${digits}e${exponent + tens}`);
}

/** The units the Probes' Unit list offers: each quantity once, in English letters, the usual ones of a probe first. */
const USUAL = ['V', 'A', 'Hz', 'dB', 'deg', 'W', 's', 'V/V', '%', 'ohm', 'F', 'm', 'J', 'count', '1'];
export function unitChoices(): string[] {
  const all = [...new Set([...Object.keys(quantities), ...Object.values(spellings).map(r => r[0])])].filter(c => c !== 'fixture');
  return [...USUAL.filter(u => all.includes(u)), ...all.filter(u => !USUAL.includes(u))];
}

const join = (number: string, written: string) => written ? `${number} ${written}` : number;

/** The power of ten a unit is of its canonical unit (um: -6) when a row in it is written with prefixes; null otherwise. */
function tenPower(unit: string): number | null {
  const rule = spellings[unit];
  if (!rule || !prefixable.has(rule[0]) || rule[2] !== 0) return null;
  const power = Math.round(Math.log10(rule[1]));
  return Math.abs(10 ** power - rule[1]) <= 1e-12 * rule[1] ? power : null;
}

/** The decimal digits and the exponent of a number, exactly as it reads back: 4.5e-7 is 45 x 10^-8. */
function decimal(v: number): { digits: string; exponent: number } {
  const [mantissa, power] = Math.abs(v).toExponential().split('e');           // the shortest digits that read back exactly
  const [whole, fraction = ''] = mantissa.split('.');
  return { digits: whole + fraction, exponent: Number(power) - fraction.length };
}

/** A stored number of a row in `unit`, written the one way: 4.5e-7 in m as 450 nm, 0.6 in um as 600 nm, 0.0004 in A as 400 uA,
 *  1e8 in Hz as 100 MHz, -30 in dB as -30 dB. `digits`: rounded to that many significant digits first (the read-only views);
 *  without, exact (the editors). */
export function quantity(value: unknown, unit: string | null | undefined, digits?: number): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return value == null ? '' : String(value);
  const v = digits ? Number(value.toPrecision(digits)) : value, u = unit ?? '', rule = spellings[u], power = tenPower(u);
  if (power === null) return join(String(v), !rule || rule[1] === 1 ? unitSymbol(u) : english(u));
  const canonical = unitSymbol(rule[0]);
  if (v === 0) return join('0', `${PREFIX[power] ?? ''}${canonical}`);       // 0 in the row's own prefix: 0 um
  const { digits: d, exponent } = decimal(v), e = exponent + power, lead = e + d.length - 1, sign = v < 0 ? '-' : '';
  if (lead < -18 || lead >= 15) return join(`${sign}${d[0]}${d.length > 1 ? `.${d.slice(1)}` : ''}e${lead}`, canonical);
  const prefix = Math.floor(lead / 3) * 3, moved = e - prefix;
  let number: string;
  if (moved >= 0) number = d + '0'.repeat(moved);
  else { const point = d.length + moved; number = point > 0 ? `${d.slice(0, point)}.${d.slice(point)}` : `0.${'0'.repeat(-point)}${d}`; }
  return join(`${sign}${number}`, `${PREFIX[prefix]}${canonical}`);
}

const NUMBER = /^([-+]?(?:\d+\.?\d*|\.\d+))(?:[eE]([-+]?\d+))?\s*(.*)$/;

function wrongUnit(text: string, typed: string, unit: string): string {
  const rule = spellings[unit], other = spellings[typed];
  const here = rule ? `${quantities[rule[0]] ?? rule[0]} (${unitLabel(unit)})` : `"${unit || 'no unit'}"`;
  return other ? `"${text}" is ${quantities[other[0]] ?? other[0]}; this row holds ${here}.`
    : `"${typed}" is not a unit the page knows; this row holds ${here}. Type the number with an SI letter (400u) or with the unit (400 uA).`;
}

/** What `text` is in `unit`, the unit its row stores: a number, null for an empty box, or why it cannot be read. A plain
 *  number (300, 4.5e-7) is in that unit - the one the Unit column shows, and what a block copied out of the table holds; with
 *  an SI letter or a unit it is exactly that (300u, 300 uA, 0.3mA in a row in A). */
export function readQuantity(text: string, unit: string | null | undefined): { value: number | null; unit?: string } | { problem: string } {
  const s = text.trim(), u = unit ?? '';
  if (s === '') return { value: null };
  const m = NUMBER.exec(s);
  if (!m) return { problem: `"${s}" is not a number: type it as 400u, 400 uA, 0.4m or 4e-4.` };
  const mantissa = m[1], typed = Number(m[2] ?? 0), rest = m[3].trim();
  const make = (tens: number) => { const n = Number(`${mantissa}e${typed + tens}`); return Number.isFinite(n) ? { value: n } : { problem: `"${s}" is out of range.` }; };
  const rule = spellings[u], power = tenPower(u);
  if (power === null) {
    // A row without a unit takes the one a typed value says (record 7.208: Specs over several Probes have no Unit column).
    if ((u === '' || !rule) && rest in spellings) return { ...make(0), unit: rest } as { value: number | null; unit: string };
    // A unit without prefixes (dB, deg, %, a count) or one the page does not know: the number as typed, an SI letter as before.
    if (rest === '') return make(0);
    if (rest === u || (rule && rest === unitSymbol(u)) || (rule && spellings[rest]?.[0] === rule[0] && spellings[rest][1] === rule[1])) return make(0);
    if (rest in LETTER) return make(LETTER[rest]);
    if (rule && spellings[rest]?.[0] === rule[0] && spellings[rest][2] === rule[2]) {
      const tens = Math.round(Math.log10(spellings[rest][1] / rule[1]));
      if (Math.abs(10 ** tens - spellings[rest][1] / rule[1]) <= 1e-12 * spellings[rest][1] / rule[1]) return make(tens);
    }
    return { problem: wrongUnit(s, rest, u) };
  }
  const canonical = rule[0], written = unitSymbol(canonical);
  let tens: number | null = null;
  if (rest === '') tens = power;
  else if (rest === canonical || rest === written) tens = 0;                   // 450 m in a length row: metres
  else if (rest in LETTER) tens = LETTER[rest];                                // 450n, 400m in a voltage row: milli
  else if (rest in spellings) {
    if (spellings[rest][0] !== canonical) return { problem: wrongUnit(s, rest, u) };
    tens = tenPower(rest);
  } else if (rest[0] in LETTER && (rest.slice(1) === canonical || rest.slice(1) === written || english(rest.slice(1)) === canonical))
    tens = LETTER[rest[0]];                                                    // 2.2 Gohm, 2.2 GΩ
  if (tens === null) return { problem: wrongUnit(s, rest, u) };
  return make(tens - power);
}
