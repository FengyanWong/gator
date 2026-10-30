// Static proof that a stylesheet whose rules were moved, merged or split still renders exactly as before (docs/plan-refactoring.md,
// package C11: styles.css regrouped by component). Not a browser check of the page: run_checks.mjs runs only *_check.mjs, and
// this proof needs the two texts it compares. The dynamic half of the proof is dom_identity_check.mjs --styles.
//
// What it proves, from the old and the new text alone:
//   1. The same declarations. Each stylesheet is flattened into declaration ATOMS in source order: (the chain of @media /
//      @supports / @container around the rule, ONE complex selector - a selector list is split -, property, value as written,
//      !important). The two multisets must be equal: nothing added, nothing lost, no value changed by a single byte.
//   2. The same winner everywhere. The k-th copy of an atom in the old text is the k-th copy in the new one. For every pair of
//      atoms whose relative order differs between the two texts, with the same importance, that set at least one longhand
//      in common (shorthands expanded to longhands BY THE BROWSER: headless Edge sets each declaration on a scratch element and
//      reads the longhand names back; `all` touches everything; a custom property is a property of its own), the order must
//      be shown not to matter by one of:
//        identical   the same property, value and importance: whichever comes later, the element gets the same value;
//        specificity the two selectors' specificities differ (Selectors 4: :is/:not/:has = their most specific argument, :where = 0,
//                    :nth-child(An+B of S) = a pseudo-class + S, pseudo-elements and the legacy :before/:after/:first-line/
//                    :first-letter count as types): the more specific one wins wherever it stands. Computed here and asked of
//                    the browser for every selector (DevTools CSS.addRule answers a rule's specificity): any disagreement fails;
//        elements    the two can never style the same element: their subject compounds name different pseudo-elements (none
//                    counts as one: `x::after` styles a box of its own), different element types, or different IDs (compared
//                    ignoring case: the pop-up windows are quirks-mode documents);
//        contexts    the two @media chains can never apply at once: each chain's simple width conditions - (min-width: Npx),
//                    (max-width: Npx), joined by `and` - give an interval of viewport widths, and the intervals do not meet.
//                    Any other condition is ignored, which can only widen the interval (sound).
//      Anything else FAILS and names the pair.
//   3. @keyframes / @font-face / @property / @counter-style / @page blocks: identical by name and content, same-name duplicates in
//      the same order. @layer, @import, @scope, CSS nesting and other at-rules are refused (this proof does not model them).
// Why that is enough: for one element and one longhand, the winner is the applicable atom with the highest importance, then the
// highest specificity, then the latest position. Among the atoms tied on importance and specificity that all apply to one element,
// every pair keeps its order (an inverted pair of them would be one of the cases above, and none of those can hold for two atoms
// that both apply to the same element with the same specificity), so the last of them - the winner - is the same atom, or an
// identical one. Comments are not declarations: the comments of the two texts are compared and listed, not judged.
//
// Run (Windows node; there is no node in WSL):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/css_order_proof.mjs)" --old <old.css> --new <new.css> [--report <file>]
//   ... css_order_proof.mjs --self-test        (also what it does with no --old/--new): small pairs that must pass and must fail,
//                                              and a table of selectors with their specificity
//   --minified: the two files are minifier output (a build's CSS bundle). A minifier drops a declaration that a later one of the
//   same rule overrides on every longhand, so every atom that a later atom with the same selector, @media chain and importance
//   overrides on every longhand (the later one parsed by the browser) is dropped from both sides first, and listed: the same
//   selector styles the same elements at the same specificity, so such an atom can never win and dropping it changes no winner.
// --report writes every inverted pair with the reason that clears it (or FAIL), the comments missing / added, and the expansions.
import { readFileSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import postcss from 'postcss';
import { check, fail, finish, launchEdge } from './lib/harness.mjs';

const args = process.argv.slice(2);
const option = name => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : null; };
const OLD = option('--old'), NEW = option('--new'), REPORT = option('--report'), MINIFIED = args.includes('--minified');
const SELF_TEST = args.includes('--self-test') || !(OLD && NEW);

// ---- selectors --------------------------------------------------------------------------------------------------------------
const SPACE = /[ \t\n\r\f]/;
/** Index just past the string that starts at s[i] (a quote). */
function skipString(s, i) {
  const quote = s[i];
  for (i++; i < s.length; i++) {
    if (s[i] === '\\') { i++; continue; }
    if (s[i] === quote) return i + 1;
  }
  throw new Error(`unterminated string in ${JSON.stringify(s)}`);
}
/** Index just past the bracket that matches s[i] ('(' or '['), strings and escapes skipped. */
function skipBlock(s, i) {
  const open = s[i], close = open === '(' ? ')' : ']';
  let depth = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === '\\') { i += 2; continue; }
    if (c === '"' || c === "'") { i = skipString(s, i); continue; }
    if (c === '(' || c === '[') depth++;
    if (c === ')' || c === ']') { depth--; if (depth === 0) { if (c !== close) throw new Error(`mismatched ${c} in ${JSON.stringify(s)}`); return i + 1; } }
    i++;
  }
  throw new Error(`unbalanced ${open} in ${JSON.stringify(s)}`);
}
/** `s` split at the commas outside brackets and strings, each part trimmed. */
function splitList(s) {
  const parts = [];
  let start = 0, i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === '\\') { i += 2; continue; }
    if (c === '"' || c === "'") { i = skipString(s, i); continue; }
    if (c === '(' || c === '[') { i = skipBlock(s, i); continue; }
    if (c === ',') { parts.push(s.slice(start, i).trim()); start = i + 1; }
    i++;
  }
  parts.push(s.slice(start).trim());
  return parts;
}
/** Whitespace runs outside strings collapsed to one space, the ends trimmed: the same selector, written one way. */
function normalSelector(s) {
  let out = '', i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === '\\') { out += s.slice(i, i + 2); i += 2; continue; }
    if (c === '"' || c === "'") { const j = skipString(s, i); out += s.slice(i, j); i = j; continue; }
    if (SPACE.test(c)) { while (i < s.length && SPACE.test(s[i])) i++; out += ' '; continue; }
    out += c; i++;
  }
  return out.trim();
}
const NAME_CHAR = /[A-Za-z0-9_\u0080-￿-]/;
function readName(s, i) {
  let out = '';
  while (i < s.length) {
    if (s[i] === '\\') { const m = /^\\([0-9a-fA-F]{1,6}[ \t\n\r\f]?|[\s\S])/.exec(s.slice(i)); out += m[0]; i += m[0].length; continue; }
    if (!NAME_CHAR.test(s[i])) break;
    out += s[i++];
  }
  return [out, i];
}
const LEGACY_PSEUDO_ELEMENTS = new Set(['before', 'after', 'first-line', 'first-letter']);
/** A complex selector as compounds of simple selectors: { compounds: [[{ kind, name, arg }]], combinators, leading }. */
function parseComplex(text) {
  const s = text.trim(), compounds = [], combinators = [];
  let current = [], leading = null, i = 0;
  const close = comb => {
    if (current.length) { compounds.push(current); current = []; combinators.push(comb); }
    else if (!compounds.length) leading = comb;                   // a relative selector, as :has() takes
    else throw new Error(`two combinators in a row in ${JSON.stringify(text)}`);
  };
  while (i < s.length) {
    const c = s[i];
    if (SPACE.test(c) || c === '>' || c === '+' || c === '~' || (c === '|' && s[i + 1] === '|')) {
      let comb = ' ';
      while (i < s.length && SPACE.test(s[i])) i++;
      if (s[i] === '>' || s[i] === '+' || s[i] === '~') { comb = s[i]; i++; }
      else if (s[i] === '|' && s[i + 1] === '|') { comb = '||'; i += 2; }
      while (i < s.length && SPACE.test(s[i])) i++;
      if (i < s.length) close(comb);
      continue;
    }
    if (c === '*' || NAME_CHAR.test(c) || c === '\\' || c === '|') {          // a type or *, perhaps with a namespace
      let name, namespace = null;
      if (c === '*') { name = '*'; i++; } else if (c === '|') { name = ''; } else [name, i] = readName(s, i);
      if (s[i] === '|' && s[i + 1] !== '|') {
        namespace = name; i++;
        if (s[i] === '*') { name = '*'; i++; } else [name, i] = readName(s, i);
      }
      current.push(name === '*' ? { kind: 'universal', namespace } : { kind: 'type', name, namespace });
      continue;
    }
    if (c === '#' || c === '.') {
      const [name, j] = readName(s, i + 1);
      if (!name) throw new Error(`empty ${c} in ${JSON.stringify(text)}`);
      current.push({ kind: c === '#' ? 'id' : 'class', name }); i = j; continue;
    }
    if (c === '[') { const j = skipBlock(s, i); current.push({ kind: 'attribute', text: s.slice(i, j) }); i = j; continue; }
    if (c === ':') {
      const element = s[i + 1] === ':';
      const [name, j] = readName(s, i + (element ? 2 : 1));
      if (!name) throw new Error(`empty pseudo in ${JSON.stringify(text)}`);
      let arg = null; i = j;
      if (s[i] === '(') { const k = skipBlock(s, i); arg = s.slice(i + 1, k - 1); i = k; }
      const lower = name.toLowerCase();
      current.push(element || LEGACY_PSEUDO_ELEMENTS.has(lower) ? { kind: 'pseudo-element', name: lower, arg } : { kind: 'pseudo-class', name: lower, arg });
      continue;
    }
    if (c === '&') throw new Error(`CSS nesting (&) is not modelled: ${JSON.stringify(text)}`);
    throw new Error(`unexpected ${JSON.stringify(c)} in selector ${JSON.stringify(text)}`);
  }
  if (current.length) compounds.push(current);
  else if (compounds.length) throw new Error(`selector ends with a combinator: ${JSON.stringify(text)}`);
  if (!compounds.length) throw new Error(`empty selector: ${JSON.stringify(text)}`);
  return { compounds, combinators, leading };
}
const ZERO = [0, 0, 0];
const add = (x, y) => [x[0] + y[0], x[1] + y[1], x[2] + y[2]];
const compare = (x, y) => x[0] - y[0] || x[1] - y[1] || x[2] - y[2];
const most = list => list.reduce((best, s) => (compare(s, best) > 0 ? s : best), ZERO);
/** The most specific selector of a selector list (the argument of :is, :not, :has, ...). */
const listSpecificity = text => most(splitList(text).map(t => specificity(parseComplex(t))));
const ARGUMENT_MAX = new Set(['is', 'not', 'has', 'matches', '-webkit-any', '-moz-any']);
function simpleSpecificity(x) {
  switch (x.kind) {
    case 'id': return [1, 0, 0];
    case 'class': case 'attribute': return [0, 1, 0];
    case 'type': return [0, 0, 1];
    case 'universal': return ZERO;
    case 'pseudo-element': return x.name === 'slotted' && x.arg ? add([0, 0, 1], listSpecificity(x.arg)) : [0, 0, 1];
    case 'pseudo-class': {
      if (x.name === 'where') return ZERO;
      if (ARGUMENT_MAX.has(x.name)) return x.arg === null ? [0, 1, 0] : listSpecificity(x.arg);
      if (/^nth-(last-)?(child|of-type)$/.test(x.name) && x.arg) {
        const of = /\sof\s/i.exec(x.arg);
        return of ? add([0, 1, 0], listSpecificity(x.arg.slice(of.index + of[0].length))) : [0, 1, 0];
      }
      if ((x.name === 'host' || x.name === 'host-context') && x.arg) return add([0, 1, 0], listSpecificity(x.arg));
      return [0, 1, 0];
    }
    default: throw new Error(`unknown simple selector ${x.kind}`);
  }
}
function specificity(parsed) {
  let total = ZERO;
  for (const compound of parsed.compounds) for (const x of compound) total = add(total, simpleSpecificity(x));
  return total;
}
/** What the subject compound says about the element it styles: its type, its IDs, its pseudo-element(s). */
function subjectOf(parsed) {
  const subject = parsed.compounds[parsed.compounds.length - 1];
  const types = subject.filter(x => x.kind === 'type');
  return {
    // a namespaced type is left unknown (it is not needed here): only plain HTML/SVG local names are compared
    type: types.length === 1 && types[0].namespace === null ? types[0].name.toLowerCase() : null,
    ids: subject.filter(x => x.kind === 'id').map(x => x.name.toLowerCase()),
    pseudo: subject.filter(x => x.kind === 'pseudo-element').map(x => `::${x.name}${x.arg === null ? '' : `(${normalSelector(x.arg)})`}`).join(''),
  };
}
/** Why two selectors can never style the same element (or box), or null. */
function neverSameElement(a, b) {
  if (a.pseudo !== b.pseudo) return `pseudo-elements ${a.pseudo || '(none)'} / ${b.pseudo || '(none)'}`;
  if (a.type && b.type && a.type !== b.type) return `types ${a.type} / ${b.type}`;
  const idA = new Set(a.ids), idB = new Set(b.ids);
  if (idA.size > 1) return `${[...idA].join(' ')}: two IDs on one element never match`;
  if (idB.size > 1) return `${[...idB].join(' ')}: two IDs on one element never match`;
  if (idA.size && idB.size && [...idA][0] !== [...idB][0]) return `ids #${[...idA][0]} / #${[...idB][0]}`;
  return null;
}

// ---- contexts (@media / @supports / @container chains) ------------------------------------------------------------------------
/** The interval of viewport widths [lo, hi] (px, inclusive) that a context's simple width conditions allow. */
function widthInterval(context) {
  let lo = -Infinity, hi = Infinity;
  for (const entry of context) {
    const m = /^@media (.*)$/i.exec(entry);
    if (!m || /^\s*not\b/i.test(m[1]) || m[1].includes(',')) continue;   // a negation or a list (OR): ignored whole (sound)
    const parts = m[1].split(/\s+and\s+/i).map(p => p.trim());
    for (const part of parts) {
      const w = /^\(\s*(min|max)-width\s*:\s*(\d+(?:\.\d+)?)px\s*\)$/i.exec(part);
      if (!w) continue;                                              // any other conjunct only narrows the set: ignored (sound)
      if (w[1].toLowerCase() === 'min') lo = Math.max(lo, Number(w[2])); else hi = Math.min(hi, Number(w[2]));
    }
  }
  return [lo, hi];
}
function neverBothApply(c1, c2) {
  const [lo1, hi1] = widthInterval(c1), [lo2, hi2] = widthInterval(c2);
  const lo = Math.max(lo1, lo2), hi = Math.min(hi1, hi2);
  return lo > hi ? `widths [${lo1}, ${hi1}] / [${lo2}, ${hi2}] px never meet` : null;
}

// ---- a stylesheet as atoms ----------------------------------------------------------------------------------------------------
const CONDITIONS = new Set(['media', 'supports', 'container']);
const NAMED_BLOCKS = new Set(['keyframes', '-webkit-keyframes', 'font-face', 'property', 'counter-style', 'page', 'font-feature-values']);
const lowerProperty = p => (p.startsWith('--') ? p : p.toLowerCase());
/** atoms: { context: [string], selector, property, value, important, position, line }; position = the declaration's ordinal. */
function flatten(text, file) {
  const root = postcss.parse(text, { from: file });
  const atoms = [], blocks = [], problems = [], comments = [];
  let position = 0, rules = 0;
  const walk = (container, context) => {
    for (const node of container.nodes ?? []) {
      if (node.type === 'comment') { comments.push(node.text); continue; }
      if (node.type === 'atrule') {
        const name = node.name.toLowerCase();
        if (CONDITIONS.has(name)) { walk(node, [...context, `@${name} ${normalSelector(node.params)}`]); continue; }
        if (NAMED_BLOCKS.has(name)) {
          const body = (node.nodes ?? []).map(n => n.toString()).join(';');
          const family = name === 'font-face' ? (node.nodes ?? []).find(n => n.type === 'decl' && n.prop.toLowerCase() === 'font-family')?.value ?? '' : '';
          blocks.push({ key: `${context.join(' / ')} @${name} ${normalSelector(node.params)} ${family}`.trim(), body: normalSelector(body), line: node.source.start.line });
          continue;
        }
        problems.push(`line ${node.source.start.line}: @${name} is not modelled by this proof`);
        continue;
      }
      if (node.type === 'rule') {
        const rule = ++rules;
        let selectors;
        try { selectors = splitList(node.selector).map(normalSelector); selectors.forEach(parseComplex); }
        catch (e) { problems.push(`line ${node.source.start.line}: ${e.message}`); continue; }
        for (const child of node.nodes ?? []) {
          if (child.type === 'comment') { comments.push(child.text); continue; }
          if (child.type !== 'decl') { problems.push(`line ${child.source.start.line}: a ${child.type} inside ${node.selector} (CSS nesting is not modelled)`); continue; }
          const value = child.raws.value?.raw ?? child.value;
          position++;
          for (const selector of selectors)
            atoms.push({ context, selector, property: lowerProperty(child.prop), value, important: !!child.important, position, rule, line: child.source.start.line });
        }
        continue;
      }
      problems.push(`line ${node.source?.start?.line}: a ${node.type} outside any rule`);
    }
  };
  walk(root, []);
  return { atoms, blocks, problems, comments };
}
const atomKey = a => JSON.stringify([a.context, a.selector, a.property, a.value, a.important]);
const describe = a => `${a.context.length ? `${a.context.join(' / ')} ` : ''}${a.selector} { ${a.property}: ${a.value}${a.important ? ' !important' : ''} }`;

// ---- what the browser says: longhands and specificity -----------------------------------------------------------------------------
/** From a headless Edge:
 *  map: { 'property\nvalue': [longhand, ...] } for every declaration, read back from a scratch element. A declaration this browser
 *    drops (an unknown property or value) keeps its own name, and a vendor-prefixed one also the unprefixed name's longhands, so
 *    that it still meets what it could override in a browser that knows it;
 *  specificity: { selector: [a, b, c] } for every complex selector, as the browser computes it (DevTools CSS.addRule into a
 *    scratch inspector stylesheet answers each selector's specificity) - the proof checks its own against it, selector by
 *    selector; `unparsed` lists the selectors the browser refused. */
async function browserFacts(declarations, selectors = []) {
  const browser = await launchEdge('css-order');
  try {
    const page = await browser.open({ consoleApi: false });
    const list = [...declarations].map(k => k.split('\n'));
    const answer = await page.evaluate(`(() => {
      const el = document.createElement('div'); document.body.appendChild(el);
      const longhands = (p, v) => { el.removeAttribute('style'); el.style.setProperty(p, v); return Array.from(el.style); };
      return ${JSON.stringify(list)}.map(([p, v]) => {
        const own = longhands(p, v);
        const bare = /^-(webkit|moz|ms|o)-/.test(p) ? p.replace(/^-(webkit|moz|ms|o)-/, '') : null;
        const plain = bare && !own.length ? longhands(bare, v) : [];
        return { own, bare, plain };
      });
    })()`);
    const map = new Map(), dropped = [];
    answer.forEach(({ own, bare, plain }, i) => {
      const [p, v] = list[i];
      if (own.length) { map.set(`${p}\n${v}`, own); return; }
      const names = new Set([p, ...(bare ? [bare, ...plain] : [])]);
      map.set(`${p}\n${v}`, [...names]);
      dropped.push(`${p}: ${v} -> ${[...names].join(', ')}`);
    });
    const specificity = new Map(), unparsed = [];
    if (selectors.length) {
      await page.send('DOM.enable'); await page.send('CSS.enable');
      const { frameTree } = await page.send('Page.getFrameTree');
      const { styleSheetId } = await page.send('CSS.createStyleSheet', { frameId: frameTree.frame.id });
      for (const selector of new Set(selectors)) {
        try {
          const { rule } = await page.send('CSS.addRule', { styleSheetId, ruleText: `${selector} {}`, location: { startLine: 0, startColumn: 0, endLine: 0, endColumn: 0 } });
          const all = rule.selectorList.selectors;
          if (all.length !== 1 || !all[0].specificity) { unparsed.push(`${selector} (read as ${all.length} selectors)`); continue; }
          const { a, b, c } = all[0].specificity;
          specificity.set(selector, [a, b, c]);
        } catch (e) { unparsed.push(`${selector} (${e.message.slice(0, 80)})`); }
      }
    }
    const parsed = new Set(answer.map(({ own }, i) => (own.length ? `${list[i][0]}\n${list[i][1]}` : null)).filter(Boolean));
    return { map, dropped, parsed, specificity, unparsed, browser: await page.evaluate('navigator.userAgent') };
  } finally { await browser.close(); }
}

// ---- the proof ----------------------------------------------------------------------------------------------------------------
/** Compares two stylesheets; returns { ok, lines (the report), numbers }. `facts` = browserFacts() of every declaration and selector. */
function prove(oldText, newText, facts, { names = ['old', 'new'], minified = false } = {}) {
  const expand = facts.map;
  const lines = [], problems = [];
  const a = flatten(oldText, names[0]), b = flatten(newText, names[1]);
  // --minified: an atom that a later atom with the same selector, in the same @media chain and with the same importance, overrides
  // on every longhand (the later declaration parsed by this browser) can never win: the same selector styles the same elements
  // at the same specificity, and the later one comes later. A minifier drops such declarations (inside a rule, after merging
  // restated rules), so they are dropped from both sides first, and listed.
  const overridden = [];
  if (minified) for (const [side, name] of [[a, names[0]], [b, names[1]]]) {
    const longhands = x => expand.get(`${x.property}\n${x.value}`) ?? [x.property];
    const bySelector = new Map();
    for (const x of side.atoms) { const k = JSON.stringify([x.context, x.selector]); if (!bySelector.has(k)) bySelector.set(k, []); bySelector.get(k).push(x); }
    const dead = new Set();
    for (const list of bySelector.values()) for (const x of list) {
      const later = list.filter(y => y.position > x.position && y.important === x.important && y.property !== 'all' && facts.parsed?.has(`${y.property}\n${y.value}`));
      if (x.property !== 'all' && longhands(x).every(l => later.some(y => longhands(y).includes(l)))) dead.add(x);
    }
    for (const x of dead) overridden.push(`${name} line ${x.line}: ${describe(x)}`);
    side.atoms.splice(0, side.atoms.length, ...side.atoms.filter(x => !dead.has(x)));
  }
  problems.push(...a.problems.map(p => `${names[0]} ${p}`), ...b.problems.map(p => `${names[1]} ${p}`));
  // 1. the same atoms
  const count = list => { const m = new Map(); for (const x of list) m.set(atomKey(x), [...(m.get(atomKey(x)) ?? []), x]); return m; };
  const ca = count(a.atoms), cb = count(b.atoms);
  const lost = [], gained = [];
  for (const [key, xs] of ca) { const n = (cb.get(key) ?? []).length; if (n < xs.length) lost.push(`${xs.length - n} x ${describe(xs[0])} (old line ${xs[0].line})`); }
  for (const [key, ys] of cb) { const n = (ca.get(key) ?? []).length; if (n < ys.length) gained.push(`${ys.length - n} x ${describe(ys[0])} (new line ${ys[0].line})`); }
  problems.push(...lost.map(x => `only in ${names[0]}: ${x}`), ...gained.map(x => `only in ${names[1]}: ${x}`));
  // 2. blocks by name, content and order of same-name duplicates
  const blockList = blocks => blocks.map(x => `${x.key} ${x.body}`);
  const sortedA = blockList(a.blocks).sort(), sortedB = blockList(b.blocks).sort();
  if (JSON.stringify(sortedA) !== JSON.stringify(sortedB)) problems.push('the @keyframes/@font-face/... blocks differ by name or content');
  for (const key of new Set(a.blocks.map(x => x.key))) {
    const order = list => list.filter(x => x.key === key).map(x => x.body).join('\n');
    if (order(a.blocks) !== order(b.blocks)) problems.push(`the blocks named ${key} are not in the same order`);
  }
  const numbers = { atoms: a.atoms.length, declarations: new Set(a.atoms.map(x => x.position)).size, blocks: a.blocks.length, inverted: 0,
    reasons: { identical: 0, importance: 0, specificity: 0, elements: 0, contexts: 0 }, failed: 0, pairsAll: 0 };
  if (problems.length) return { ok: false, lines: [...lines, ...problems.map(p => `PROBLEM ${p}`)], numbers, problems, overridden };
  // the k-th copy of an atom in the old text is the k-th copy in the new one
  const newPosition = new Map();
  for (const [key, xs] of ca) xs.forEach((x, k) => newPosition.set(x, cb.get(key)[k].position));
  const parsed = new Map(), subject = new Map(), spec = new Map(), disagree = [];
  for (const x of a.atoms) if (!parsed.has(x.selector)) {
    const p = parseComplex(x.selector), mine = specificity(p), theirs = facts.specificity?.get(x.selector);
    parsed.set(x.selector, p); subject.set(x.selector, subjectOf(p)); spec.set(x.selector, mine);
    if (!theirs) disagree.push(`${x.selector}: the browser gave no specificity`);
    else if (compare(mine, theirs) !== 0) disagree.push(`${x.selector}: the browser ${theirs.join(',')}, this proof ${mine.join(',')}`);
  }
  numbers.selectors = parsed.size;
  if (disagree.length) { problems.push(...disagree.map(d => `specificity ${d}`)); return { ok: false, lines: problems.map(p => `PROBLEM ${p}`), numbers, problems, overridden }; }
  const longhandsOf = new Map();
  for (const x of a.atoms) {
    const k = `${x.property}\n${x.value}`;
    if (!expand.has(k)) throw new Error(`no expansion for ${k}`);
    longhandsOf.set(x, x.property === 'all' ? ['all'] : expand.get(k));
  }
  // atoms per longhand ('all' meets every one); then every pair that changed order
  const byLonghand = new Map(), everything = [];
  for (const x of a.atoms) for (const l of longhandsOf.get(x)) {
    if (l === 'all') { everything.push(x); continue; }
    if (!byLonghand.has(l)) byLonghand.set(l, []);
    byLonghand.get(l).push(x);
  }
  const index = new Map(a.atoms.map((x, i) => [x, i]));
  const total = a.atoms.length, shared = new Set(), report = [];
  /** One pair of atoms that share a longhand (x before y in the old text's atom order), judged once. */
  const judge = (x, y, longhand) => {
    const key = index.get(x) * total + index.get(y);
    if (shared.has(key)) return;
    shared.add(key);
    const before = Math.sign(x.position - y.position), after = Math.sign(newPosition.get(x) - newPosition.get(y));
    if (before === after) return;                                    // the same order (or the same declaration in both): nothing to prove
    numbers.inverted++;
    let reason = null, kind = null;
    if (x.important !== y.important) { kind = 'importance'; reason = 'one is !important'; }
    else if (x.property === y.property && x.value === y.value) { kind = 'identical'; reason = 'the same declaration'; }
    else {
      const s1 = spec.get(x.selector), s2 = spec.get(y.selector);
      if (compare(s1, s2) !== 0) { kind = 'specificity'; reason = `specificity ${s1.join(',')} / ${s2.join(',')}`; }
      else {
        const why = neverSameElement(subject.get(x.selector), subject.get(y.selector));
        if (why) { kind = 'elements'; reason = why; }
        else { const ctx = neverBothApply(x.context, y.context); if (ctx) { kind = 'contexts'; reason = ctx; } }
      }
    }
    if (kind) numbers.reasons[kind]++; else numbers.failed++;
    report.push(`${kind ? 'ok  ' : 'FAIL'} ${kind ?? 'unproved'}: ${reason ?? 'the same specificity, may style the same element, may apply together'}  [${longhand}]\n`
      + `       old line ${x.line} (declaration ${x.position} -> ${newPosition.get(x)}): ${describe(x)}\n`
      + `       old line ${y.line} (declaration ${y.position} -> ${newPosition.get(y)}): ${describe(y)}`);
  };
  for (const [longhand, xs] of byLonghand)
    for (let i = 0; i < xs.length; i++) for (let j = i + 1; j < xs.length; j++) judge(xs[i], xs[j], longhand);
  for (const x of everything) for (const y of a.atoms) if (x !== y) judge(...(index.get(x) < index.get(y) ? [x, y] : [y, x]), 'all');
  numbers.pairsAll = shared.size;
  lines.push(...report);
  return { ok: numbers.failed === 0, lines, numbers, problems, comments: [a.comments, b.comments], overridden };
}

// ---- the self-test --------------------------------------------------------------------------------------------------------------
const SPECIFICITY_TABLE = [
  ['*', [0, 0, 0]], ['li', [0, 0, 1]], ['ul li', [0, 0, 2]], ['ul ol+li', [0, 0, 3]], ['h1 + *[rel=up]', [0, 1, 1]],
  ['ul ol li.red', [0, 1, 3]], ['li.red.level', [0, 2, 1]], ['#x34y', [1, 0, 0]], ['#s12:not(FOO)', [1, 0, 1]],
  ['.foo :is(.bar, #baz)', [1, 1, 0]], [':where(#a) .b', [0, 1, 0]], ['a::after', [0, 0, 2]], ['a:before', [0, 0, 2]],
  [':root[data-theme] :where(.tabs > button:not(.run-list-button))', [0, 2, 0]],
  ['table.editor :is(th, td):is([data-field="variable_id"], [data-field="metric_id"])', [0, 2, 2]],
  ['table.editor:not(:has(td.issues > .issue)) td.issues', [0, 4, 3]], ['button:has(> svg.icon)', [0, 1, 2]],
  ['tr:nth-child(even)', [0, 1, 1]], ['li:nth-child(2n+1 of .a, #b)', [1, 1, 1]], ['input.bounded::-webkit-inner-spin-button', [0, 1, 2]],
  ['dialog.graph-dialog::backdrop', [0, 1, 2]], [':where(table.grid.small, table.editor) :where(tbody tr:nth-child(even)) > td', [0, 0, 1]],
  ['.scroll.scrolled-x > table.editor :is(th, td):is([data-field="a"], [data-field="b"])::after', [0, 4, 3]],
  ['#connection-root', [1, 0, 0]], ['input[type=checkbox]', [0, 1, 1]], ['svg|rect', [0, 0, 1]], ['*|*', [0, 0, 0]],
];
const PAIRS = [   // [what, old, new, must pass]
  ['an unrelated rule moved', '.a{color:red} .b{margin:0}', '.b{margin:0} .a{color:red}', true],
  ['two equal selectors on one property swapped', '.a{color:red} .b{color:blue}', '.b{color:blue} .a{color:red}', false],
  ['different specificity swapped', '.a{color:red} .b.c{color:blue}', '.b.c{color:blue} .a{color:red}', true],
  ['a shorthand and its longhand swapped', '.a{margin:0} .b{margin-top:1px}', '.b{margin-top:1px} .a{margin:0}', false],
  ['two shorthands that share longhands swapped', '.a{border:1px solid red} .b{border-left:2px dotted blue}', '.b{border-left:2px dotted blue} .a{border:1px solid red}', false],
  ['font and line-height swapped', '.a{font:12px/1 serif} .b{line-height:2}', '.b{line-height:2} .a{font:12px/1 serif}', false],
  ['different element types swapped', 'td{color:red} th{color:blue}', 'th{color:blue} td{color:red}', true],
  ['a type and a class of equal specificity swapped', 'td .a{color:red} th.a{color:blue}', 'th.a{color:blue} td .a{color:red}', false],
  ['different IDs swapped', '#a{color:red} #b{color:blue}', '#b{color:blue} #a{color:red}', true],
  ['IDs that differ only in case swapped (quirks mode)', '#a{color:red} #A{color:blue}', '#A{color:blue} #a{color:red}', false],
  ['disjoint @media swapped', '@media (min-width: 1101px){.a{color:red}} @media (max-width: 1100px){.a{color:blue}}', '@media (max-width: 1100px){.a{color:blue}} @media (min-width: 1101px){.a{color:red}}', true],
  ['overlapping @media swapped', '@media (max-width: 1100px){.a{color:red}} @media (max-width: 700px){.a{color:blue}}', '@media (max-width: 700px){.a{color:blue}} @media (max-width: 1100px){.a{color:red}}', false],
  ['a rule moved past an @media rule that overrides it', '.a{color:red} @media (max-width: 700px){.a{color:blue}}', '@media (max-width: 700px){.a{color:blue}} .a{color:red}', false],
  ['different importance swapped', '.a{color:red !important} .b{color:blue}', '.b{color:blue} .a{color:red !important}', true],
  ['two !important declarations swapped', '.a{color:red !important} .b{color:blue !important}', '.b{color:blue !important} .a{color:red !important}', false],
  ['a value changed', '.a{color:red}', '.a{color:#f00}', false],
  ['a declaration lost', '.a{color:red;margin:0}', '.a{color:red}', false],
  ['a declaration added', '.a{color:red}', '.a{color:red;margin:0}', false],
  ['a restated selector merged', '.a{color:red} .b{margin:0} .a{padding:0}', '.a{color:red;padding:0} .b{margin:0}', true],
  ['a merge that jumps over a conflict', '.a{color:red} .b{color:blue} .a{color:green}', '.a{color:red;color:green} .b{color:blue}', false],
  ['a pseudo-element and its element swapped', '.a::after{color:red} .a{color:blue}', '.a{color:blue} .a::after{color:red}', true],
  ['the same pseudo-element swapped', '.a::after{color:red} .b::after{color:blue}', '.b::after{color:blue} .a::after{color:red}', false],
  ['legacy :after is ::after', '.a:after{color:red} .b::after{color:blue}', '.b::after{color:blue} .a:after{color:red}', false],
  ['`all` swapped with anything', '.a{all:unset} .b{color:red}', '.b{color:red} .a{all:unset}', false],
  ['identical declarations swapped', '.a{color:red} .b{color:red}', '.b{color:red} .a{color:red}', true],
  ['a selector list split apart', '.a,.b{color:red}', '.b{color:red} .a{color:red}', true],
  ['custom properties swapped', '.a{--x:1px} .b{--x:2px}', '.b{--x:2px} .a{--x:1px}', false],
  ['different custom properties swapped', '.a{--x:1px} .b{--y:2px}', '.b{--y:2px} .a{--x:1px}', true],
  ['a prefix this browser drops meets its unprefixed property', '.a{-moz-appearance:none} .b{appearance:auto}', '.b{appearance:auto} .a{-moz-appearance:none}', false],
  ['an alias meets its property', '.a{-webkit-appearance:none} .b{appearance:auto}', '.b{appearance:auto} .a{-webkit-appearance:none}', false],
  [':where() lowers specificity to a tie', ':where(.x) .a{color:red} .b{color:blue}', '.b{color:blue} :where(.x) .a{color:red}', false],
  [':is() raises specificity', ':is(#x) .a{color:red} .b{color:blue}', '.b{color:blue} :is(#x) .a{color:red}', true],
  ['@keyframes changed', '@keyframes k{from{opacity:0}}', '@keyframes k{from{opacity:1}}', false],
  ['same-name @keyframes reordered', '@keyframes k{from{opacity:0}} @keyframes k{from{opacity:1}}', '@keyframes k{from{opacity:1}} @keyframes k{from{opacity:0}}', false],
  ['@layer refused', '@layer x{.a{color:red}}', '@layer x{.a{color:red}}', false],
  ['nesting refused', '.a{color:red; .b{color:blue}}', '.a{color:red; .b{color:blue}}', false],
  ['a rule moved inside the same @media', '@media (max-width: 700px){.a{color:red} .b{margin:0}}', '@media (max-width: 700px){.b{margin:0} .a{color:red}}', true],
  ['an @media rule moved past a rule it overrides', '.a{color:red} @media (min-width: 1101px){.a{color:blue}}', '@media (min-width: 1101px){.a{color:blue}} .a{color:red}', false],
  // --minified: what a minifier does to a merged rule (drops the overridden declaration), and what it may not do
  ['minified: a merged rule without its overridden declaration', '.a{padding:1px} .b{color:red} .a{padding:2px}', '.a{padding:2px} .b{color:red}', true, true],
  ['the same pair is refused without --minified', '.a{padding:1px} .b{color:red} .a{padding:2px}', '.a{padding:2px} .b{color:red}', false],
  ['minified: a declaration only partly overridden is not dropped', '.a{border:1px solid red} .a{border-width:2px}', '.a{border-width:2px}', false, true],
  ['minified: overridden only in another @media is not dropped', '.a{padding:1px} @media (max-width: 700px){.a{padding:2px}}', '@media (max-width: 700px){.a{padding:2px}}', false, true],
];
async function selfTest() {
  for (const [selector, want] of SPECIFICITY_TABLE) {
    let got = null;
    try { got = specificity(parseComplex(selector)); } catch (e) { got = e.message; }
    check(`self-test: specificity of ${selector} is ${want.join(',')}`, JSON.stringify(got) === JSON.stringify(want), JSON.stringify(got));
  }
  const declarations = new Set(), selectors = new Set(SPECIFICITY_TABLE.map(([selector]) => selector));
  const atoms = text => { try { return flatten(text, 'test').atoms; } catch { return []; } };
  for (const [, o, n] of PAIRS) for (const x of [...atoms(o), ...atoms(n)]) { declarations.add(`${x.property}\n${x.value}`); selectors.add(x.selector); }
  const facts = await browserFacts(declarations, [...selectors]);
  // the browser computes the table's specificities too (a namespaced selector needs an @namespace rule: the browser refuses it here)
  for (const [selector, want] of SPECIFICITY_TABLE) {
    if (selector.includes('|')) continue;
    const theirs = facts.specificity.get(selector);
    check(`self-test: the browser agrees: ${selector} is ${want.join(',')}`, JSON.stringify(theirs) === JSON.stringify(want), JSON.stringify(theirs ?? null));
  }
  for (const [what, o, n, pass, minified = false] of PAIRS) {
    let result;
    try { result = prove(o, n, facts, { names: ['old', 'new'], minified }); } catch (e) { result = { ok: false, lines: [`ERROR ${e.message}`] }; }
    check(`self-test: ${what} ${pass ? 'passes' : 'fails'}`, result.ok === pass, result.ok ? 'it passed' : result.lines.join(' | ').slice(0, 400));
  }
}

// The pieces, for a script that plans a regroup with the same rules (they decide nothing on their own).
export { flatten, parseComplex, specificity, subjectOf, neverSameElement, neverBothApply, browserFacts, prove, splitList, normalSelector, compare };

// ---- main (only when run as a script) ----------------------------------------------------------------------------------------
if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) try {
  if (SELF_TEST) await selfTest();
  if (OLD && NEW) {
    const oldText = readFileSync(OLD, 'utf8'), newText = readFileSync(NEW, 'utf8');
    const declarations = new Set(), selectors = new Set();
    for (const text of [oldText, newText]) for (const x of flatten(text, 'x').atoms) { declarations.add(`${x.property}\n${x.value}`); selectors.add(x.selector); }
    const facts = await browserFacts(declarations, [...selectors]);
    const { map, dropped, browser } = facts;
    const result = prove(oldText, newText, facts, { names: [OLD, NEW], minified: MINIFIED });
    const n = result.numbers;
    if (MINIFIED) console.log(`INFO  --minified: atoms a later atom with the same selector overrides on every longhand, dropped from both sides first (${result.overridden?.length ?? 0}): ${result.overridden?.length ? result.overridden.join('; ') : 'none'}`);
    console.log(`INFO  ${browser}`);
    console.log(`INFO  ${n.atoms} atoms (${n.declarations} declarations, selector lists split), ${n.blocks} named blocks; ${declarations.size} distinct declarations expanded by the browser`);
    console.log(`INFO  ${n.selectors ?? '?'} distinct selectors: the browser's specificity of each equals this proof's${facts.unparsed.length ? `; refused by the browser: ${facts.unparsed.join('; ')}` : ''}`);
    if (dropped.length) console.log(`INFO  declarations this browser drops, kept under their own (and unprefixed) names: ${dropped.join('; ')}`);
    console.log(`INFO  ${n.pairsAll} pairs of atoms share a longhand; ${n.inverted} of them changed order: `
      + `${Object.entries(n.reasons).map(([k, v]) => `${k} ${v}`).join(', ')}, unproved ${n.failed}`);
    for (const p of result.problems) console.log(`PROBLEM ${p}`);
    for (const l of result.lines.filter(l => l.startsWith('FAIL')).slice(0, 40)) console.log(l);
    check(`the same declarations, each value byte for byte (${n.atoms} atoms)`, !result.problems.length, `${result.problems.length} problem(s)`);
    check(`every pair that changed order is proved not to matter (${n.inverted} pairs)`, result.ok && !result.problems.length, `${n.failed} unproved`);
    if (result.comments) {
      const [ca, cb] = result.comments.map(list => list.map(c => c.replace(/\s+/g, " ").trim()));
      const left = ca.filter(c => !cb.includes(c)), added = cb.filter(c => !ca.includes(c));
      console.log(`INFO  comments: ${ca.length} old, ${cb.length} new; ${left.length} old comment(s) not found verbatim in the new text, ${added.length} new one(s)`);
      for (const c of left) console.log(`INFO    old only: ${c.slice(0, 160)}`);
      for (const c of added) console.log(`INFO    new only: ${c.slice(0, 160)}`);
    }
    if (REPORT) {
      writeFileSync(REPORT, [`old ${OLD}`, `new ${NEW}`, `browser ${browser}`, JSON.stringify(n), ...result.problems.map(p => `PROBLEM ${p}`),
        `dropped: ${dropped.join('; ') || 'none'}`, '', ...result.lines, '',
        'expansions:', ...[...map].map(([k, v]) => `  ${k.replace('\n', ': ')} -> ${v.join(' ')}`)].join('\n') + '\n');
      console.log(`INFO  report: ${REPORT}`);
    }
  }
} catch (error) { fail(error); } finally { finish(); }
