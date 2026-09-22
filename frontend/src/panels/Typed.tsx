import { InputHTMLAttributes, useEffect, useState } from 'react';
import { Json } from '../api';

/** A box that keeps what is being TYPED while it has focus. "1." and "4.5e-" are steps towards 1.5 and 4.5e-7, JSON is not
 *  valid before its closing bracket, "a," is on its way to a list of two, and an emptied box is about to get a new text.
 *  Boxes that showed the stored value after every key turned "1." into "1" (typing 1.5 gave 15), swallowed commas and put
 *  "unspecified" back while the box was being cleared (review of 2026-09-22). The value gets every text that parses; the
 *  stored value comes back on blur, and at once when it changes from outside - undo, import, the agent - focus or not. */
export function Typed({ value, format, parse, onChange, ...box }: {
  value: Json; format: (v: Json) => string; parse: (text: string) => { value: Json } | undefined; onChange: (v: Json) => void;
} & Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange' | 'onBlur'>) {
  const [text, setText] = useState<string | null>(null);
  const typed = text === null ? undefined : parse(text);
  const stale = typed !== undefined && format(typed.value) !== format(value);
  useEffect(() => { if (stale) setText(null); }, [stale]);
  return <input {...box} value={text !== null && !stale ? text : format(value)} onBlur={() => setText(null)}
    onChange={e => { setText(e.target.value); const next = parse(e.target.value); if (next !== undefined) onChange(next.value); }} />;
}
