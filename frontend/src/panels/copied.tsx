// A click that copies says what came of it (branch record SIF-94): "copied" for 1.5 s when the clipboard took the text, "could
// not copy" when the browser refused it. Run status's and the Runs window's run folder said "copied" (SIF-54), while the RL
// model window's folders, Output settings' paths and the like said nothing either way, so a refused copy showed only at the paste.
import { useEffect, useRef, useState } from 'react';
import { copy } from '../api';

/** `from`: the window the clicks happen in, whose own clipboard takes the text (api.ts copy). `copyText(text, key)` copies;
 *  `word(key)` is the word to put after what was clicked, for the last copy of that key only - another path's or another
 *  run's cell says nothing. The key is the text itself unless one is given. */
export function useCopied(from?: Window | null) {
  const [said, setSaid] = useState<{ key: string; ok: boolean } | null>(null);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const copyText = (text: string, key = text) => copy(text, from).then(() => true, () => false).then(ok => {
    window.clearTimeout(timer.current);
    setSaid({ key, ok });
    timer.current = window.setTimeout(() => setSaid(null), 1500);
  });
  const word = (key: string) => said?.key !== key ? null : said.ok ? <b className="copy-word ok"> copied</b>
    : <b className="copy-word warn" title="The browser refused the clipboard: select the text and copy it with Ctrl+C."> could not copy</b>;
  return { copyText, word };
}
