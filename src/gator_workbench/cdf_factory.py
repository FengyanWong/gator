"""The run's environment factory for a task written by the PDK's property form (see ``cdf_write``).

It lives apart from ``cdf_write`` because its base class comes from ``analog_optimizer.training.parallel``, which imports
torch and PyG: about 2 s at every start of a process that imports it. The short-lived processes that only prepare or check
a cell - the check before every run, Check now, the corner check - use ``cdf_write`` without this class and so skip that
import (review of 2026-09-30). ``cdf_write.factory_class`` returns this class for a run, and
``cdf_write.CdfNativeEnvironmentFactory`` still names it.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace

from analog_optimizer.training.parallel import NativeEnvironmentFactory

from .cdf_write import preparation_session


@dataclass(frozen=True)
class CdfNativeEnvironmentFactory(NativeEnvironmentFactory):
    """`NativeEnvironmentFactory` whose preparation service writes with the workbench's adapter for the task
    (`cdf_write.backend_class`: the form writer's, or the verified one under the cell's lock); the lanes are unchanged."""

    @contextmanager
    def preparation_context(self, limits, report):
        with preparation_session(self.config, self.profile, limits, report) as service:
            yield replace(self, preparation=service)
