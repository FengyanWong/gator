import { FormEvent, useEffect, useRef, useState } from 'react';
import { parseTotal } from '../launch';
import { count } from '../format';
import { Icon } from './Icons';

/** The budget form of Continue... (record 7.261; plan "Existing runs: continued in place"), instead of the browser's
 *  prompt: "Used 800 · New total [1,200] · Allows 400 more". Whole numbers only - 1,200 reads as 1200 - and the total
 *  must be more than the evaluations used; what is wrong is said on the form, and nothing is sent. The field holds the
 *  run's own total while some of it is left (Continue unchanged), and starts empty when it is used up. `used` and `total`
 *  come from the continuation check - the evaluations of the save point Continue goes on from - or, with a backend that
 *  has no such check, from the run's status. `blocked`: why Continue cannot go now (launch.ts readiness), or null. */
export function ContinueForm({ used, total, blocked, onContinue, onCancel }: { used: number | null; total: number | null;
  blocked: string | null; onContinue: (total: number | null) => void; onCancel: () => void }) {
  const exhausted = used != null && total != null && used >= total;
  const [text, setText] = useState(exhausted || total == null ? '' : String(total));
  const [pressed, setPressed] = useState(false);              // the error is said as it is typed, and once more on a press
  const field = useRef<HTMLInputElement>(null);
  useEffect(() => { field.current?.focus(); field.current?.select(); }, []);
  const parsed = parseTotal(text, used, total);
  const newTotal = parsed.error ? null : parsed.value ?? total;
  const more = newTotal != null && used != null ? newTotal - used : null;
  const error = parsed.error && (pressed || text.trim()) ? parsed.error : null;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setPressed(true);
    if (!parsed.error && !blocked) onContinue(parsed.value === total ? null : parsed.value);     // the run's own total = unchanged
  };
  // Used and Allows as Run status writes its counts (branch record SIF-117); the field and its hint keep the digits one types.
  return <form className="continue-form" onSubmit={submit} onKeyDown={e => { if (e.key === 'Escape') onCancel(); }}>
    <span>Used <b>{used != null ? count(used) : '?'}</b></span>
    <label>New total <input ref={field} inputMode="numeric" value={text} aria-invalid={!!error} placeholder={used != null ? `more than ${used}` : ''}
      onChange={e => setText(e.target.value)} title="The new total budget of evaluations: whole evaluations, more than the ones used. Empty = unchanged." /></label>
    <span className="continue-allows">{more != null ? `Allows ${count(more)} more` : ''}</span>
    <button type="submit" className="primary" disabled={!!blocked}
      title={blocked ? `Continue: ${blocked}` : 'Continue: The run goes on in its own folder from its saved state, with its own saved configuration and this total.'}>
      <Icon name="play" label="Continue" /></button>
    <button type="button" onClick={onCancel} title="Cancel: Nothing is sent; the run stays as it is.">Cancel</button>
    {error && <p className="error continue-error" role="alert">{error}</p>}
  </form>;
}
