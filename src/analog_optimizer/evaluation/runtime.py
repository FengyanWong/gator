"""Picklable benchmark environments, using the same native preparation service as training."""
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path


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
