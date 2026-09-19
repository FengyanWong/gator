"""Verified GPDK045 v6.0 OTA profile; not a general PDK parameter setter."""
from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from analog_optimizer.netlist.config import ParserConfig
from analog_optimizer.netlist.expressions import evaluate
from analog_optimizer.netlist.spectre_parser import SpectreParser
from .backend import UnsupportedCapability
from .conditions import PVTCorner, SimulationCondition

INPUT_KEYS = (("XU1/M1", "w"), ("XU1/M2", "w"))
GEOMETRY = ("ad", "as", "pd", "ps", "nrd", "nrs", "sa", "sb", "sd", "sca", "scb", "scc")


def number(value):
    return evaluate(str(value), {}.__getitem__)


def equal(a, b):
    return math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-24)


class Gpdk045OtaProfile:
    """Only the input-pair width is writable; all other exported fields are fixed."""

    def __init__(self, *, design_file: Path, mapping_file: Path,
                 reference_structure: Path, reference_readback: Path,
                 width_bounds=(3.6e-6, 4.4e-6), width_step=5e-9,
                 conditions_file: Path | None = None):
        self.design = json.loads(Path(design_file).read_text())
        self.reference = json.loads(Path(reference_readback).read_text())
        conditions_file = conditions_file or Path(mapping_file).with_name('gpdk045_conditions.json')
        self.condition_config = json.loads(Path(conditions_file).read_text())
        self.nominal_corner = PVTCorner(**self.condition_config['nominal'])
        if not equal(self.nominal_corner.supply_v, number(self.design['supply_v'])):
            raise ValueError('Nominal condition must match the baseline testbench supply')
        self.parser = SpectreParser(ParserConfig.from_file(mapping_file))
        self.graph = self.parser.parse_file(reference_structure)
        self.graph.validate()
        self.width_bounds = tuple(width_bounds)
        # Explicit software action grid for this profile. A real CDF probe rounded
        # 4.106791753 um to 4.105 um; arbitrary floating proposals are not writable.
        # This does not claim the minimum legal manufacturing grid of every device.
        self.width_step = width_step
        if (len(self.width_bounds) != 2 or not all(math.isfinite(x) for x in self.width_bounds)
                or not 0 < self.width_bounds[0] < self.width_bounds[1]):
            raise ValueError("Invalid width bounds")
        if not math.isfinite(width_step) or width_step <= 0 or any(
                not self._on_width_grid(v) for v in self.width_bounds):
            raise ValueError("Width bounds must lie on a finite positive width grid")
        self.validate_readback(self.reference)
        self.validate_export(Path(reference_structure), self.reference)

    def validate_condition(self, condition):
        if not isinstance(condition, SimulationCondition):
            raise ValueError('Explicit typed simulation condition required')
        if condition.monte_carlo is not None:
            raise UnsupportedCapability('GPDK045 MC interface reserved; statistical execution and sample parsing are not validated')
        policy, corner = self.condition_config['model_policy'], condition.corner
        if corner.model_section not in policy['deterministic_sections']:
            raise ValueError('Model section is not a verified GPDK045 deterministic corner')
        for value, bounds, name in ((corner.temperature_c, policy['temperature_c_bounds'], 'temperature'),
                                   (corner.supply_v, policy['screening_supply_v_bounds'], 'supply')):
            if not bounds[0] <= value <= bounds[1]:
                raise ValueError(f'{name} outside the configured GPDK045 screening envelope')
        if condition.nominal_only and corner != self.nominal_corner:
            raise ValueError('Nominal evaluation cannot silently change PVT conditions')

    def structure_for_condition(self, structure, condition):
        """Prepare a job-local supply override after validating the native export.

        The schematic and matched dimensions stay untouched. VINP/VINN=0.6 V,
        VBIAS=0.4 V and load=1 pF remain absolute: no implicit supply tracking.
        This narrowly scoped transformation is not a general Spectre editor.
        """
        self.validate_condition(condition)
        if equal(condition.corner.supply_v, self.nominal_corner.supply_v):
            return structure
        pattern = r'(?m)^(VDD\s+\(VDD\s+0\)\s+vsource\b[^\n]*?\bdc=)([^\s]+)'
        updated, count = re.subn(pattern, lambda m: m[1] + format(condition.corner.supply_v, '.12g'), structure)
        if count != 1:
            raise ValueError('Expected exactly one explicit VDD source for the condition override')
        before, after = self.parser.parse_text(structure), self.parser.parse_text(updated)
        for device, parameters in before.parameters.items():
            for name, value in parameters.items():
                actual = after.parameters[device][name]
                if (device, name) == ('VDD', 'dc'):
                    if not actual.valid or not equal(actual.value, condition.corner.supply_v):
                        raise ValueError('Supply override did not reach the exported graph')
                elif (actual.value, actual.raw) != (value.value, value.raw):
                    raise ValueError('Unexpected parameter change during condition preparation')
        return updated

    @staticmethod
    def instances(snapshot):
        result = {i['name']: i for i in snapshot['instances']}
        if len(result) != len(snapshot['instances']):
            raise ValueError("Duplicate schematic instances")
        return result

    def assignments(self, width):
        result = {key: width for key in INPUT_KEYS}
        self.validate_assignment(result)
        return result

    def optimization_graph(self, structure=None):
        """Constrain the graph action contract to the verified writable pair."""
        graph = self.parser.parse_file(structure) if structure is not None else deepcopy(self.graph)
        graph.parameter_groups = [
            replace(group, lower=self.width_bounds[0], upper=self.width_bounds[1],
                    scale='linear', step=self.width_step, mutable=True) if group.id == 'input_pair_width'
            else replace(group, mutable=False)
            for group in graph.parameter_groups
        ]
        graph.validate()
        writable = graph.assignments({g.id: g.value for g in graph.parameter_groups if g.mutable})
        self.validate_assignment(writable)
        return graph

    def _on_width_grid(self, width):
        return math.isclose(width / self.width_step, round(width / self.width_step), rel_tol=0, abs_tol=1e-7)

    def validate_assignment(self, parameters):
        if set(parameters) != set(INPUT_KEYS):
            raise ValueError("Only a complete M1/M2 matched width assignment is supported")
        values = list(parameters.values())
        if any(not math.isfinite(x) or not self.width_bounds[0] <= x <= self.width_bounds[1]
               for x in values) or not equal(*values):
            raise ValueError("Widths must match and lie inside the configured bounds")
        if any(not self._on_width_grid(x) for x in values):
            raise ValueError("Widths must lie on the configured CDF-compatible width grid")

    def validate_readback(self, snapshot):
        actual, reference = self.instances(snapshot), self.instances(self.reference)
        if set(actual) != set(reference) or set(actual) != {'M1', 'M2', 'M3', 'M4', 'M5'}:
            raise ValueError("Unexpected OTA instance set")
        for name, inst in actual.items():
            ref = reference[name]
            for key in ('lib', 'cell', 'view', 'terms'):
                if inst[key] != ref[key]:
                    raise ValueError(f"Unexpected {name} {key}")
            params = inst['params']
            for key in ('l', 'm', 'fingers') + (() if name in ('M1', 'M2') else ('w', 'fw') + GEOMETRY):
                if not equal(number(params[key]), number(ref['params'][key])):
                    raise ValueError(f"Unexpected fixed parameter {name}.{key}")
            if not equal(number(params['fw']), number(params['w'])):
                raise ValueError(f"Stale finger width on {name}")
            for key in GEOMETRY:
                if number(params[key]) <= 0:
                    raise ValueError(f"Invalid derived geometry {name}.{key}")
        parameters = {(f'XU1/{name}', 'w'): number(actual[name]['params']['w']) for name in ('M1', 'M2')}
        self.validate_assignment(parameters)
        return parameters

    def verify_transition(self, before, after, expected):
        actual = self.validate_readback(after)
        if any(not equal(actual[k], v) for k, v in expected.items()):
            raise ValueError("CDF width readback differs from requested values")
        old, new = self.instances(before), self.instances(after)
        for name in ('M1', 'M2'):
            a, b = old[name]['params'], new[name]['params']
            if not equal(number(a['w']), number(b['w'])):
                for key in ('ad', 'as', 'pd', 'ps', 'nrd', 'nrs'):
                    if equal(number(a[key]), number(b[key])):
                        raise ValueError(f"Stale derived geometry {name}.{key}")

    def validate_export(self, structure, snapshot):
        graph = self.parser.parse_file(structure)
        graph.validate()
        def topology(g):
            return (sorted((d.id, d.model_ref, d.terminals) for d in g.devices),
                    sorted((c.device_id, c.terminal, c.net_id) for c in g.connections))
        if topology(graph) != topology(self.graph):
            raise ValueError("Exported topology differs from the verified reference")
        snapshot_instances = self.instances(snapshot)
        for device, params in graph.parameters.items():
            ref = self.graph.parameters[device]
            if params.keys() != ref.keys():
                raise ValueError(f"Exported parameter set changed on {device}")
            for key, param in params.items():
                if device in ('XU1/M1', 'XU1/M2') and key in ('w',) + GEOMETRY:
                    expected = number(snapshot_instances[device.split('/')[1]]['params'][key])
                    same = param.valid and equal(param.value, expected)
                elif param.valid and ref[key].valid:
                    same = equal(param.value, ref[key].value)
                else:
                    same = param.raw == ref[key].raw
                if not same:
                    raise ValueError(f"Exported parameter mismatch: {device}.{key}")
        return self.validate_readback(snapshot)

def set_gpdk_mos(client, library, cell, name, width, length):
    """GPDK045 needs PasCdfFormInit before its callbacks and doneProc.

    Signatures were read from the installed IC23.1 / GPDK045 v6.0 session.
    Do not silently suppress callback errors or reuse this for another PDK.
    """
    from virtuoso_bridge.virtuoso.ops import escape_skill_string as esc
    values = {k: esc(v) for k, v in dict(lib=library, cell=cell, name=name,
                                        width=width, length=length).items()}
    # PAS requires instance CDF and cdfgForm=nil, verified against Cadence's
    # support explanation: https://community.cadence.com/cadence_technology_forums/f/custom-ic-skill/31459
    skill = '''let((cv inst cdfgData cdfgForm)
      cv = dbOpenCellViewByType("{lib}" "{cell}" "schematic" "schematic" "a")
      unwindProtect(progn(
        inst = car(setof(x cv~>instances x~>name == "{name}"))
        unless(inst error("instance not found"))
        cdfgData = cdfGetInstCDF(inst)
        cdfgForm = nil
        unless(cdfgData~>formInitProc == "PasCdfFormInit" error("Unexpected PDK init callback"))
        PasCdfFormInit(cdfgData)
        cdfgData~>l~>value = "{length}"
        gpdk045_mosCB('l)
        cdfgData~>fingers~>value = "1"
        gpdk045_mosCB('fingers)
        cdfgData~>fw~>value = "{width}"
        gpdk045_mosCB('fw)
        cdfgData~>m~>value = "1"
        gpdk045_mosCB('m)
        PasCdfDone(inst)
        schCheck(cv)
        unless(dbSave(cv) error("Save failed"))
        t
      ) when(cv dbClose(cv))))'''.format(**values)
    result = client.execute_skill(skill, timeout=30)
    if not result.ok or result.output.strip() != "t":
        raise RuntimeError("GPDK045 parameter callback/save failed: " + "; ".join(result.errors))
