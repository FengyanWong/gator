"""Picklable benchmark environments, using the same native preparation service as training."""
from contextlib import contextmanager
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class BenchmarkFactory:
    origin: str
    config: object = None
    profile: object = None
    preparation: object = None
    timeout_seconds: float = 120

    @property
    def parallel_safe(self):
        return self.origin == 'synthetic' or self.preparation is not None

    @contextmanager
    def preparation_context(self, limits, report):
        if self.origin == 'synthetic':
            yield self
        else:
            from analog_optimizer.backends.native_preparation import preparation_session
            with preparation_session(self.config, self.profile, limits, report) as service:
                yield replace(self, preparation=service)

    def __call__(self, task, steps, output):
        return self.create_recorded(task, steps, output, None)

    def create_recorded(self, task, steps, output, recorder):
        from analog_optimizer.envs.sizing import CircuitSizingEnv
        if self.origin == 'synthetic':
            from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
            backend = SyntheticSizingBackend(task.graph, targets={'w': .4, 'c': -.3})
        elif self.preparation is not None:
            from analog_optimizer.backends.native_preparation import NativeCandidateBackend
            backend = NativeCandidateBackend(self.config, self.profile, self.preparation)
        else:
            from analog_optimizer.backends.virtuoso_bridge import VirtuosoBridgeBackend
            backend = VirtuosoBridgeBackend(self.config, self.profile)
        return CircuitSizingEnv(backend, task.graph, task.specs, output, max_steps=steps,
                                timeout_seconds=self.timeout_seconds, stop_on_success=False,
                                expected_origin=self.origin, recorder=recorder)


@dataclass
class BaselineCheck:
    metrics: dict
    netlist_sha256: str | None = None

    def __call__(self, record):
        import math
        actual = record['metrics']
        if (not record.get('evaluation_valid') or actual.keys() != self.metrics.keys() or any(
                not ((value is None and self.metrics[key] is None) or
                     (value is not None and self.metrics[key] is not None and
                      math.isclose(value, self.metrics[key], rel_tol=1e-6, abs_tol=1e-12)))
                for key, value in actual.items())):
            raise RuntimeError('Baseline metrics differ from the verified reference')
        if self.netlist_sha256 is None:
            self.netlist_sha256 = record['netlist_sha256']
        elif record['netlist_sha256'] != self.netlist_sha256:
            raise RuntimeError('Baseline netlist differs from the verified reference')


@dataclass
class TaskBaselineChecks:
    """Each real circuit retains its own verified metrics and executed deck."""
    checks: dict

    def for_task(self, task):
        return self.checks[task.id]


@dataclass(frozen=True)
class MultiCircuitFactory:
    """Sequential native CDF episodes across independently qualified circuits.

    Each episode acquires the shared Virtuoso session lock and restores its
    circuit on exit. No overlapping preparation services own that session.
    """
    factories: dict
    parallel_safe: bool = False

    def __call__(self, task, steps, output):
        return self.create_recorded(task, steps, output, None)

    def create_recorded(self, task, steps, output, recorder):
        from analog_optimizer.envs.sizing import graph_contract
        factory = self.factories[task.id]
        if factory.origin != 'real' or factory.preparation is not None:
            raise ValueError('Multi-circuit factory requires serialized native real backends')
        if graph_contract(task.graph) != graph_contract(factory.profile.optimization_graph()):
            raise ValueError('Task graph does not match its qualified circuit profile')
        return factory.create_recorded(task, steps, output, recorder)
