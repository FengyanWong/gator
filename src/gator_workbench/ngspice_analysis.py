"""Count reached ngspice control commands without changing their numerical settings."""
from collections import Counter
import re

PREFIX = 'GATOR_ANALYSIS_DISPATCH'
COMMANDS = ('op', 'dc', 'ac', 'tran', 'noise', 'pz', 'sens', 'disto', 'tf')


def instrument(text):
    """Insert command markers before analysis-related commands in ngspice control blocks."""
    lines, control = [], False
    for line in text.splitlines(keepends=True):
        token = line.strip().split(maxsplit=1)
        command = token[0].lower() if token else ''
        if command == '.control':
            control = True
        elif command == '.endc':
            control = False
        elif control and command in (*COMMANDS, 'run', 'resume', 'source'):
            lines.append(f'echo {PREFIX} {command}\n')
        lines.append(line)
    return ''.join(lines)


def counts(stdout, *, complete):
    """Summarize reached command markers and report an analysis total only when it is known."""
    reached = Counter(re.findall(rf'(?m)^{PREFIX} ({"|".join((*COMMANDS, "run", "resume", "source"))})\s*$', stdout))
    # run/resume may launch several analyses. Never equate one such command to one analysis.
    known = bool(reached) and not any(k in reached for k in ('run', 'resume', 'source'))
    return dict(commands=dict(reached), analyses=sum(reached.values()) if complete and known else None,
                complete=bool(complete and known),
                meaning='Reached analysis command invocations, including failed attempts; incomplete output gives only a lower bound.')
