"""The row-by-row difference of two configurations' tables, as the editors show it (Matched devices, Import JSON, the rows
not saved in the task). Moved here from the Agent tab's proposals on 2026-10-06 (record 7.226), which no longer exist."""
from __future__ import annotations

from .schema import SECTION_KEYS


def structured_diff(before: dict, after: dict) -> list:
    diff = []
    for section, id_field in SECTION_KEYS.items():
        old = {row[id_field]: row for row in before.get(section, [])}
        new = {row[id_field]: row for row in after.get(section, [])}
        for key in sorted(set(old) | set(new)):
            if key not in old:
                diff.append(dict(section=section, key=key, change='added', fields=[
                    dict(field=f, before=None, after=v) for f, v in new[key].items()]))
            elif key not in new:
                diff.append(dict(section=section, key=key, change='removed', fields=[
                    dict(field=f, before=v, after=None) for f, v in old[key].items()]))
            else:
                fields = [dict(field=f, before=old[key].get(f), after=new[key].get(f))
                          for f in sorted(set(old[key]) | set(new[key])) if old[key].get(f) != new[key].get(f)]
                if fields:
                    diff.append(dict(section=section, key=key, change='modified', fields=fields))
    return diff
