// Check of the one way of writing a quantity (record 7.208): frontend/src/units.ts, imported AS IT IS - Windows node strips its
// types - with the table the backend under test sends (GET /api/schema `unit_forms`). The written cases are those of
// tests/workbench/test_wb_unit_text.py, so the editors and the backend's messages write every quantity alike. No browser.
//   - a stored number is written with its own digits, an SI prefix and its unit, in English letters (450 nm, 9.535 kohm,
//     60 deg, 0 um, 1e-21 m; user: "dont use greek characters for unit, use english letters instead");
//   - what is written reads back to the stored number exactly; 450n, 0.45 µm, 4.5e-7 and a plain number (in the row's
//     unit) are read; another quantity and an unknown unit are refused in words, the examples in the row's own unit
//     (branch record SIF-49), and a cell's tooltip names the unit a plain number is in;
//   - a unit changed to another of the same quantity moves a number exactly; the Unit column writes µm as um, kΩ as kohm.
// Run: WSLENV=GATOR_WORKBENCH_URL GATOR_WORKBENCH_URL=http://127.0.0.1:<preview>/ "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/unit_text_check.mjs)"
//   (the default URL is the live 8765, which needs a backend started after record 7.208 for its table)
import { check, finish, workbenchUrl } from './lib/harness.mjs';

const units = await import(new URL('../src/units.ts', import.meta.url).href);
const APP = await workbenchUrl();
const forms = (await (await fetch(new URL('api/schema', APP))).json()).unit_forms;
check('the backend sends its unit table with the schema', !!forms?.spellings?.um, JSON.stringify(Object.keys(forms ?? {})));
units.setUnitForms(forms);
const { quantity, readQuantity, convert, unitLabel, sameUnit, knownUnit, unitChoices } = units;

const CASES = [  // stored number, the row's unit, as it is written - tests/workbench/test_wb_unit_text.py CASES
  [4.5e-7, 'm', '450 nm'], [0.6, 'um', '600 nm'], [1.205, 'um', '1.205 um'], [0.045, 'um', '45 nm'], [20.0, 'um', '20 um'],
  [0.01, 'um', '10 nm'], [0.0004, 'A', '400 uA'], [1e8, 'Hz', '100 MHz'], [1.1e9, 'Hz', '1.1 GHz'], [-30.0, 'dB', '-30 dB'],
  [60.0, 'deg', '60 deg'], [9535.0, 'ohm', '9.535 kohm'], [477.0, 'ohm', '477 ohm'], [0.22, 'V', '220 mV'], [0.032, 'V', '32 mV'],
  [1.2, 'V', '1.2 V'], [-1e9, 'Hz/V', '-1 GHz/V'], [12, 'count', '12'], [0.006, '1', '0.006'], [45.0, '%', '45 %'],
  [400.0, 'V/V', '400 V/V'], [5.0, 'mV/V', '5 mV/V'], [0.0005, 'W', '500 uW'], [0.0, 'um', '0 um'], [0.0, 'A', '0 A'],
  [1e-21, 'm', '1e-21 m'], [3.3e16, 'Hz', '3.3e16 Hz'], [999e12, 'Hz', '999 THz'], [27.0, 'degC', '27 degC'], [4.99e-14, 'F', '49.9 fF'],
  [0.5, 'pF', '500 fF'], [0.001, 'm', '1 mm'], [-0.00045, 'A', '-450 uA'], [0.1 + 0.2, 'V', '300.00000000000004 mV'],
];
const wrong = CASES.filter(([v, u, w]) => quantity(v, u) !== w).map(([v, u, w]) => `${v} ${u}: ${quantity(v, u)} (backend: ${w})`);
check(`the page writes all ${CASES.length} cases as the backend does`, !wrong.length, wrong.join('; '));
const back = CASES.filter(([v, u, w]) => { const r = readQuantity(w, u); return !('value' in r) || r.value !== v; })
  .map(([v, u, w]) => `${w} in ${u}: ${JSON.stringify(readQuantity(w, u))}`);
check('what is written reads back to the stored number exactly', !back.length, back.join('; '));

const read = (text, unit) => { const r = readQuantity(text, unit); return 'value' in r ? r.value : r.problem; };
const READS = [  // typed, the row's unit, the stored number
  ['450n', 'm', 4.5e-7], ['450 nm', 'm', 4.5e-7], ['450nm', 'm', 4.5e-7], ['0.45 µm', 'm', 4.5e-7], ['0.45u', 'm', 4.5e-7], ['4.5e-7', 'm', 4.5e-7],
  ['0.000002', 'm', 0.000002], ['450 m', 'm', 450], ['450n', 'um', 0.45], ['0.6', 'um', 0.6], ['600 nm', 'um', 0.6], ['400 uA', 'A', 0.0004],
  ['400uA', 'A', 0.0004], ['0.4mA', 'A', 0.0004], ['400u', 'A', 0.0004], ['4e-4', 'A', 0.0004], ['300', 'A', 300], ['400m', 'V', 0.4],
  ['2.2 kΩ', 'ohm', 2200], ['2.2k', 'ohm', 2200], ['2.2 kohm', 'ohm', 2200], ['2.2 GΩ', 'ohm', 2.2e9], ['2.2 Gohm', 'ohm', 2.2e9], ['0.45 um', 'm', 4.5e-7], ['60 deg', 'deg', 60], ['60 deg', 'deg', 60],
  ['-30 dB', 'dB', -30], ['45 %', '%', 45], ['5 mV/V', 'V/V', 0.005], ['12', 'count', 12], ['', 'm', null],
];
const misread = READS.filter(([t, u, v]) => read(t, u) !== v).map(([t, u, v]) => `"${t}" in ${u}: ${read(t, u)} (expected ${v})`);
check(`${READS.length} typed forms are read into the row's unit`, !misread.length, misread.join('; '));
check('another quantity is refused in words', read('200 mV', 'A') === '"200 mV" is a voltage; this row holds a current (A).', read('200 mV', 'A'));
check('an unknown unit is refused in words', String(read('3 furlong', 'm')).startsWith('"furlong" is not a unit the page knows; this row holds a length (m).'), read('3 furlong', 'm'));
check('what is not a number is refused in words', String(read('abc', 'm')).startsWith('"abc" is not a number'), read('abc', 'm'));
// The refusals' examples are in the row's own unit, and a row without one is said in words (branch record SIF-49: "400 uA"
// was offered in a length row, which refuses it; a row without a unit was "no unit" in quotes).
check('...with the forms a number takes, the example in the row\'s own unit (a length row: 0.5 m, not 400 uA)',
  read('abc', 'm') === '"abc" is not a number: type it plain (0.5), with an exponent (2.5e-6), an SI letter (2.5u) or this row\'s unit (0.5 m).'
  && read('abc', 'count') === '"abc" is not a number: type it plain (0.5), with an exponent (2.5e-6) or an SI letter (2.5u).', `${read('abc', 'm')} | ${read('abc', 'count')}`);
check('an unknown unit\'s example is the row\'s own unit; a row without a unit says so in words',
  String(read('3 furlong', 'm')).endsWith('Type the number with an SI letter (400u) or with this row\'s unit (400 m).')
  && read('3 furlong', '') === '"furlong" is not a unit the page knows; this row has no unit. Type the number with an SI letter (400u) or with a unit the page knows (400 uA).'
  && read('3 furlong', 'count') === '"furlong" is not a unit the page knows; this row holds a count. Type the number with an SI letter (400u) or plain (400).',
  `${read('3 furlong', 'm')} | ${read('3 furlong', '')} | ${read('3 furlong', 'count')}`);
const { plainNumberIn } = units;
check('a cell\'s tooltip names the unit a plain number is in: the row\'s own, not the prefix the cell shows (branch record SIF-49)',
  plainNumberIn('m') === 'A plain number here is in m.' && plainNumberIn('um') === 'A plain number here is in um.' && plainNumberIn('kΩ') === 'A plain number here is in kohm.'
  && plainNumberIn('count') === '' && plainNumberIn(null).startsWith('This row has no unit yet'), ['m', 'um', 'kΩ', 'count', null].map(u => `${u}: ${plainNumberIn(u)}`).join(' | '));

check('a unit changed within its quantity moves the number exactly', convert(0.6, 'um', 'nm') === 600 && convert(2e-6, 'm', 'um') === 2 && convert(3, 'nm', 'um') === 0.003
  && convert(0.0004, 'A', 'µA') === 400 && convert(1, 'A', 'V') === null && convert(60, 'deg', '°') === 60,
  JSON.stringify([convert(0.6, 'um', 'nm'), convert(2e-6, 'm', 'um'), convert(3, 'nm', 'um'), convert(0.0004, 'A', 'µA')]));
const LABELS = [['um', 'um'], ['µm', 'um'], ['ohm', 'ohm'], ['kΩ', 'kohm'], ['deg', 'deg'], ['°', 'deg'], ['uA', 'uA'], ['count', 'count'], ['1', '1'], ['m', 'm'], ['MHz', 'MHz']];
check('the Unit column writes a unit in English letters (µm as um, kΩ as kohm, ° as deg), a count by name', LABELS.every(([u, l]) => unitLabel(u) === l), LABELS.map(([u]) => `${u}: ${unitLabel(u)}`).join(', '));
check('the same unit spelled otherwise is the same unit; µm and nm are not', sameUnit('um', 'µm') && sameUnit('deg', '°') && !sameUnit('um', 'nm') && knownUnit('kΩ') && !knownUnit('furlong'));
check('the Unit column offers each quantity once, in English letters, fixture units left out', unitChoices().includes('ohm') && unitChoices().includes('deg')
  && !unitChoices().some(u => /[µμΩ°]/.test(u)) && !unitChoices().includes('fixture')
  && new Set(unitChoices()).size === unitChoices().length, unitChoices().join(' '));
finish();
