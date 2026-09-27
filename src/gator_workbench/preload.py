"""Import the optimizer stack once, in ONE thread, before the backend serves a request.

Every heavy import of the workbench is lazy (inside a function), which keeps the CLI and the pure-data
modules light. The API however runs its endpoints in a thread pool, so the first page load made two
threads import `torch_geometric` for the first time at once: `/api/meta` (version report) and, 0.5 s
later, `/api/config/validate` (`analog_optimizer.models`). CPython resolves concurrent imports of a
package that has internal import cycles by handing one thread a partially initialized module. Both
requests failed, and the half-imported package then broke EVERY later import in that process
(`partially initialized module 'torch_geometric' has no attribute 'typing'`) until a restart.

A completely imported module is safe to import from any thread, so the cure is order, not locking:
`create_app` calls `preload()` before it starts a thread or accepts a request (about 2 s, once per
process). An import error is not swallowed: a backend that cannot import the optimizer can neither
validate nor start anything, and the start-up traceback names the real cause.

`virtuoso_bridge` is deliberately absent. It is optional, lives in a profile-configured
site-packages, and finding it is layer 1 of the connection check.
"""
from __future__ import annotations

import importlib
import threading

# Top-level packages whose lazy imports must be listed in MODULES (tests/workbench/test_wb_preload.py
# scans the workbench source and fails on a lazy import that is missing here).
GUARDED_PACKAGES = ('analog_optimizer', 'torch', 'torch_geometric', 'numpy', 'pyarrow')

MODULES = (
    'numpy', 'pyarrow', 'pyarrow.parquet', 'torch', 'torch_geometric',
    'torch_geometric.nn',                             # structure table of a saved model (model_structure.py)
    'analog_optimizer.backends.conditions',           # training corners of a run (compile.py, tasks.py)
    'analog_optimizer.backends.spectre_validation',   # generated profiles (recipes.py)
    'analog_optimizer.backends.native_preparation',    # the form writer's preparation session (cdf_write.py)
    'analog_optimizer.backends.synthetic_sizing',
    'analog_optimizer.backends.virtuoso_bridge',      # the adapter only; it does not import `virtuoso_bridge`
    'analog_optimizer.envs.sizing',
    'analog_optimizer.evaluation.benchmark',
    'analog_optimizer.graph.circuit_graph',
    'analog_optimizer.graph.pyg_converter',
    'analog_optimizer.measurements.ldo',              # generated profiles (recipes.py)
    'analog_optimizer.measurements.specs',
    'analog_optimizer.measurements.vco',              # generated profiles (recipes.py)
    'analog_optimizer.models',
    'analog_optimizer.models.encoders',               # structure table of a saved model (model_structure.py)
    'analog_optimizer.models.graph_transformer',      # structure table of a saved model (model_structure.py)
    'analog_optimizer.models.inputs',
    'analog_optimizer.netlist.config',
    'analog_optimizer.netlist.expressions',
    'analog_optimizer.netlist.spectre_parser',
    'analog_optimizer.parameters.actions',            # generated profiles (generic_profile.py)
    'analog_optimizer.recording',
    'analog_optimizer.training.parallel',
    'analog_optimizer.training.replay',
    'analog_optimizer.training.sac',
    'analog_optimizer.training.workers',
)

_lock = threading.Lock()
_done = False


def preload():
    """Idempotent; the first call in a process pays for the imports, later calls return at once."""
    global _done
    with _lock:
        if _done:
            return
        for name in MODULES:
            importlib.import_module(name)
        _done = True
