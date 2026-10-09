"""The two saved MOCK models encoder_models_check reads (record 7.292): a GraphGPS and a parameter-group cross-attention
network, as small as the check expects (hidden 16, 2 heads, 1 layer, rwse), each the model of one short MOCK run under
<root>. run_checks.sh runs this before its backends start and lets backend A read <root>; before, every batch failed
that check at its guard ("Use a scratch backend and output root."), since nothing made its models.

    python encoder_models.py <root>

Run from the repository root with PYTHONPATH=src, GATOR_WORKBENCH_SYNTHETIC_FIXTURES naming the tests' stand-in task
(the workbench has no MOCK task of its own since record 7.128) and GATOR_WORKBENCH_SETTINGS_DIR naming a scratch folder
(a prepared run remembers its output root there). MOCK data only: nothing is simulated."""
import os
import sys
from pathlib import Path

MOCK_TASK = 'synthetic:gpdk045_ota5'
ENCODERS = ('graph_gps', 'group_cross_attention')


def make(root: Path) -> list[Path]:
    import torch
    from gator_workbench import runs, schema, tasks
    from gator_workbench.engine import RunEngine
    from gator_workbench.paths import OutputRoots
    torch.set_num_threads(1)
    made = []
    for encoder in ENCODERS:
        raw = tasks.starter_config(MOCK_TASK)
        raw['run'].update(max_evaluations=12, seed=11, network=dict(encoder_type=encoder, hidden_dim=16, heads=2, layers=1,
                                                                    structural_encoding='rwse'))
        raw['run']['advanced'] = dict(batch_size=4, warmup_transitions=4, episode_length=3)
        raw['output'] = dict(output_root=str(root), experiment_name=f'encoder-models-{encoder}', flush_every_evaluations=4)
        config = schema.WorkbenchConfig.model_validate(raw)
        layout, _ = runs.prepare_run(config, OutputRoots([root], include_default=False))
        state = RunEngine(layout.run_dir, task=tasks.load_task(config.circuit), lock=runs.take_lock(layout.run_dir)).run()
        if state != 'completed':
            raise SystemExit(f'the {encoder} MOCK run ended {state}: {layout.run_dir}')
        made.append(layout.run_dir)
    return made


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    for name in ('GATOR_WORKBENCH_SETTINGS_DIR', 'GATOR_WORKBENCH_SYNTHETIC_FIXTURES'):
        if not os.environ.get(name):
            raise SystemExit(f'{name} must be set (see the docstring)')
    for run_dir in make(Path(sys.argv[1]).resolve()):
        print(run_dir)
