"""The common first designs of every run (plan section 6: "the same immutable start, legal domain ... fixed eight-design
initialization"; "generate and freeze the initial legal designs by seed before running a method").

Per case and rollout seed: points of a scrambled Sobol sequence in the unit cube (`torch.quasirandom.SobolEngine`, the
generator TuRBO's own first designs come from), as proposals z = 2u - 1, legalized by the optimizer's `ActionMapper`.
A point that lands on the start design or on an earlier point after the grid projection is skipped (and recorded), so
the list holds `count` distinct legal designs. Every method's run evaluates its start design (the existing baseline),
then these designs, then its own proposals.
"""
from __future__ import annotations

from .coords import design_key

FORMAT = 'archive-compare-initial-designs-v1'


def initial_designs(mapper, groups, start: dict, *, seed: int, count: int = 8, max_draws: int = 1024) -> dict:
    """{format, seed, count, designs: [{index, draw, proposal, group_values, projected_groups}], skipped: [...]}.
    `groups`: `coords.group_rows` of the compiled task (their order is the action order). Designs are told apart by
    their grid points (`coords.design_key`), so the start design is recognized whatever its last binary digit."""
    import torch
    group_ids = [group['id'] for group in groups]
    sobol = torch.quasirandom.SobolEngine(len(group_ids), scramble=True, seed=int(seed))
    key = lambda values: design_key(groups, values)
    seen, designs, skipped = {key(start)}, [], []
    for draw in range(max_draws):
        if len(designs) == count:
            break
        u = sobol.draw(1, dtype=torch.float64)[0].tolist()
        proposal = {g: max(-1.0, min(1.0, 2.0 * v - 1.0)) for g, v in zip(group_ids, u)}
        legal = mapper.legalize(proposal)
        values = {g: legal.group_values[g] for g in group_ids}
        if key(values) in seen:
            skipped.append(dict(draw=draw, reason='start design' if key(values) == key(start) else 'an earlier design'))
            continue
        seen.add(key(values))
        designs.append(dict(index=len(designs), draw=draw, proposal=proposal, group_values=values,
                            projected_groups=list(legal.projected_groups)))
    if len(designs) < count:
        raise ValueError(f'Only {len(designs)} distinct legal designs in {max_draws} draws')
    return dict(format=FORMAT, seed=int(seed), count=count, generator='torch.quasirandom.SobolEngine(scramble=True)',
                torch_version=torch.__version__, group_ids=list(group_ids), designs=designs, skipped=skipped)
