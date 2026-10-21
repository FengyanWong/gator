// The editors' formula bar (plan-refactoring C6, out of Editors.tsx).
import { useEffect, useRef, useState } from 'react';

/** What the formula bar shows of the chosen cell: where it is, its whole value as text, whether it is typed there, and why not. */
export type BarCell = { id: string; where: string; text: string; editable: boolean; why: string; format: string };

/** The editors' formula bar (record 7.175, user: "add excel like single cell whole row text edit somewhere for long text editing
 *  which cant show everything in the cell"): the chosen cell's whole value in a box as wide as the table, as in a spreadsheet.
 *  What is typed there goes into the cell when Enter, Tab or leaving the box takes it - one Undo step - and Esc keeps the cell
 *  as it was. A list, a tick box and a value that follows another field are shown here, not typed. */
export function FormulaBar({ cell, commit, back }: { cell: BarCell | null; commit: (text: string) => string | null; back: () => void }) {
  const [draft, setDraft] = useState<string | null>(null);         // null: not typing here, the box shows the cell's value
  const [problem, setProblem] = useState<string | null>(null);
  // The text is read from a ref too: Enter and Esc go back to the cell, which blurs the box at once, and that blur must see the
  // text already taken or dropped - read from the render it would write a text Esc had just dropped.
  const typed = useRef<string | null>(null);
  const keep = (text: string | null) => { typed.current = text; setDraft(text); };
  useEffect(() => { keep(null); setProblem(null); }, [cell?.id]);  // another cell: its own value
  const take = () => {
    if (typed.current === null) return true;
    const refused = commit(typed.current);
    setProblem(refused);
    if (!refused) keep(null);
    return !refused;
  };
  return (
    <div className="formula">
      <div className="formula-bar">
        {/* The box ends a long location in "..." (a column's label and a long Probe or Spec ID; branch record SIF-66): the
            tooltip gives the column's format, then the whole location. */}
        <span className="formula-where" title={cell ? `${cell.format}\n\n${cell.where}` : 'Click a cell of the table to see its whole value here.'}>{cell ? cell.where : 'No cell chosen'}</span>
        <textarea rows={1} spellCheck={false} aria-label="Whole value of the chosen cell" disabled={!cell} readOnly={!cell?.editable}
          value={draft ?? cell?.text ?? ''} placeholder={cell ? '' : 'Click a cell to see and edit its whole value here'}
          title={!cell ? undefined : cell.editable ? 'The whole value of the chosen cell. Enter (or Tab, or clicking elsewhere) writes it into the cell; Esc keeps the cell as it was.' : cell.why}
          onChange={e => { keep(e.target.value.replace(/\r?\n/g, ' ')); setProblem(null); }}
          onKeyDown={e => {
            if (e.key === 'Enter') { e.preventDefault(); if (take()) back(); }
            else if (e.key === 'Escape') { e.preventDefault(); keep(null); setProblem(null); back(); }
            else if (e.key === 'Tab' && !take()) e.preventDefault();
          }}
          onBlur={take} />
      </div>
      {problem && <p className="error formula-problem">{problem}</p>}
    </div>);
}
