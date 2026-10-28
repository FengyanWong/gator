"""The matrix and budget contract of the comparison (plan sections 6 and 8), and its check.

Panel A: per case and replicate, five searches of 800 (T0, T+, M+, RA+, RF+). Panel B: per case and replicate, a
portfolio of four children of 200 for T+, RA+ and RF+ (one child per goal view, run one after another, so at most four
simulator lanes per portfolio), and M+'s Panel A search scored again (an alias, no new job). Replicates pair a
pretraining seed with a rollout seed: (0, 101), (1, 102), (2, 103). The goal order of a portfolio rotates with the
replicate. Seed 0 (replicate 0) of every cell runs first. The check (`check`) refuses any matrix that breaks a rule.
"""
from __future__ import annotations

from collections import Counter

FORMAT = 'archive-compare-matrix-v1'
REPLICATES = ((0, 101), (1, 102), (2, 103))
PANEL_A_METHODS = ('T0', 'T+', 'M+', 'RA+', 'RF+')
PORTFOLIO_METHODS = ('T+', 'RA+', 'RF+')
GOALS = ('portfolio_1', 'portfolio_2', 'portfolio_3', 'portfolio_4')
SEARCH_BUDGET, CHILD_BUDGET = 800, 200
LANES = 4
QUALIFICATION_PER_CASE, CONFIRMATIONS_PER_SEARCH = 5, 3
METHOD_KIND = {'T0': 'turbo_archive_v1 (empty archive)', 'T+': 'turbo_archive_v1', 'M+': 'mobo_qlognehvi_v1',
               'RA+': 'GraphGPS-SAC fine-tune', 'RF+': 'GraphGPS-SAC frozen'}
ARCHIVE = {'T0': False, 'T+': True, 'M+': True, 'RA+': True, 'RF+': True}


def goal_order(replicate: int) -> list:
    """The goal views of a portfolio in the order its children run: replicate k starts at goal k mod 4."""
    return [GOALS[(replicate + i) % len(GOALS)] for i in range(len(GOALS))]


def matrix(cases) -> dict:
    """Every job and analysis cell for `cases` (case short names, e.g. ('ldo', 'amp', 'dff'))."""
    jobs, cells = [], []
    for case in cases:
        for k, (pretrain_seed, rollout_seed) in enumerate(REPLICATES):
            common = dict(case=case, replicate=k, pretrain_seed=pretrain_seed, rollout_seed=rollout_seed,
                          stage='seed 0' if k == 0 else 'seeds 1-2', lanes=LANES)
            for method in PANEL_A_METHODS:
                job_id = f'{case}-A-{method}-r{k}'
                jobs.append(dict(common, job_id=job_id, panel='A', method=method, kind=METHOD_KIND[method],
                                 uses_archive=ARCHIVE[method], view='panel_a', parent=None,
                                 max_evaluations=SEARCH_BUDGET, max_launches=SEARCH_BUDGET,
                                 model_seed=pretrain_seed if method in ('RA+', 'RF+') else None))
                cells.append(dict(cell_id=f'{case}-A-{method}-r{k}', panel='A', case=case, method=method, replicate=k,
                                  search=job_id, jobs=[job_id]))
            for method in PORTFOLIO_METHODS:
                parent = f'{case}-B-{method}-r{k}'
                children = []
                for order, view in enumerate(goal_order(k)):
                    child = f'{parent}-c{order}-{view}'
                    children.append(child)
                    jobs.append(dict(common, job_id=child, panel='B', method=method, kind=METHOD_KIND[method],
                                     uses_archive=ARCHIVE[method], view=view, parent=parent, child_order=order,
                                     max_evaluations=CHILD_BUDGET, max_launches=CHILD_BUDGET,
                                     model_seed=pretrain_seed if method in ('RA+', 'RF+') else None))
                cells.append(dict(cell_id=parent, panel='B', case=case, method=method, replicate=k, search=parent,
                                  jobs=children, parent_budget=SEARCH_BUDGET))
            mobo = f'{case}-A-M+-r{k}'
            cells.append(dict(cell_id=f'{case}-B-M+-r{k}', panel='B', case=case, method='M+', replicate=k,
                              search=mobo, jobs=[], alias_of=mobo,
                              note='the same M+ search as Panel A, scored again for Panel B; no new job'))
    searches = sorted({cell['search'] for cell in cells})
    return dict(format=FORMAT, cases=list(cases), replicates=[list(r) for r in REPLICATES], jobs=jobs, cells=cells,
                searches=searches, budget=budget(jobs, cases))


def budget(jobs, cases) -> dict:
    """Summarize search, qualification and confirmation launch ceilings for the full matrix and seed-0 stage."""
    search = sum(job['max_launches'] for job in jobs)
    stage0 = sum(job['max_launches'] for job in jobs if job['replicate'] == 0)
    searches = len({job['parent'] or job['job_id'] for job in jobs})
    stage0_searches = len({job['parent'] or job['job_id'] for job in jobs if job['replicate'] == 0})
    qualification = QUALIFICATION_PER_CASE * len(cases)
    return dict(search_launches=search, qualification_launches=qualification,
                confirmation_launches=CONFIRMATIONS_PER_SEARCH * searches,
                maximum_physical_launches=search + qualification + CONFIRMATIONS_PER_SEARCH * searches,
                seed0_stage=dict(search_launches=stage0, confirmation_launches=CONFIRMATIONS_PER_SEARCH * stage0_searches,
                                 qualification_launches=qualification,
                                 maximum=stage0 + CONFIRMATIONS_PER_SEARCH * stage0_searches + qualification),
                assumption='one nominal simulator launch per candidate (to be confirmed per bench before authorization)')


def check(m) -> list:
    """Every broken rule of matrix `m`, in words ([] when it holds)."""
    problems = []
    jobs, cells = m['jobs'], m['cells']
    n_cases = len(m['cases'])
    ids = Counter(job['job_id'] for job in jobs)
    problems += [f'duplicate job {j}' for j, n in ids.items() if n > 1]
    a = [job for job in jobs if job['panel'] == 'A']
    b = [job for job in jobs if job['panel'] == 'B']
    expect = dict(panel_a_jobs=len(PANEL_A_METHODS) * len(REPLICATES) * n_cases,
                  portfolio_children=len(PORTFOLIO_METHODS) * len(GOALS) * len(REPLICATES) * n_cases)
    if len(a) != expect['panel_a_jobs']:
        problems.append(f"{len(a)} Panel A jobs, expected {expect['panel_a_jobs']}")
    if len(b) != expect['portfolio_children']:
        problems.append(f"{len(b)} portfolio children, expected {expect['portfolio_children']}")
    for job in a:
        if (job['max_evaluations'], job['max_launches']) != (SEARCH_BUDGET, SEARCH_BUDGET) or job['view'] != 'panel_a':
            problems.append(f"{job['job_id']}: a Panel A search has 800/800 on view panel_a")
    by_parent = {}
    for job in b:
        by_parent.setdefault(job['parent'], []).append(job)
        if (job['max_evaluations'], job['max_launches']) != (CHILD_BUDGET, CHILD_BUDGET):
            problems.append(f"{job['job_id']}: a child has 200/200")
    for parent, children in by_parent.items():
        views = [c['view'] for c in sorted(children, key=lambda c: c['child_order'])]
        if sorted(views) != sorted(GOALS):
            problems.append(f'{parent}: its children are not the four goal views once each')
        if views != goal_order(children[0]['replicate']):
            problems.append(f'{parent}: its goal order is not the rotation of replicate {children[0]["replicate"]}')
        if sum(c['max_launches'] for c in children) != SEARCH_BUDGET:
            problems.append(f'{parent}: its children do not add up to 800')
        if len({(c['method'], c['case'], c['replicate']) for c in children}) != 1:
            problems.append(f'{parent}: its children differ in method, case or replicate')
    for job in jobs:
        seeds = REPLICATES[job['replicate']]
        if (job['pretrain_seed'], job['rollout_seed']) != seeds:
            problems.append(f"{job['job_id']}: seeds {job['pretrain_seed']}/{job['rollout_seed']} are not replicate {seeds}")
        if job['lanes'] != LANES:
            problems.append(f"{job['job_id']}: {job['lanes']} lanes")
        if job['method'] in ('RA+', 'RF+') and job['model_seed'] != job['pretrain_seed']:
            problems.append(f"{job['job_id']}: an SAC arm loads the model of its pretraining seed")
        if job['uses_archive'] != ARCHIVE[job['method']]:
            problems.append(f"{job['job_id']}: archive use differs from its method")
    aliases = [cell for cell in cells if cell.get('alias_of')]
    if len(aliases) != len(REPLICATES) * n_cases or any(cell['alias_of'] not in ids or cell['jobs'] for cell in aliases):
        problems.append('every case and replicate has exactly one M+ Panel B alias of its Panel A M+ search, with no job')
    searches = {cell['search'] for cell in cells}
    if len(cells) != (len(PANEL_A_METHODS) + len(PORTFOLIO_METHODS) + 1) * len(REPLICATES) * n_cases:
        problems.append(f'{len(cells)} analysis cells')
    if len(searches) != (len(PANEL_A_METHODS) + len(PORTFOLIO_METHODS)) * len(REPLICATES) * n_cases:
        problems.append(f'{len(searches)} distinct searches')
    if m['budget'] != budget(jobs, m['cases']):
        problems.append('the budget does not follow from the jobs')
    return problems
