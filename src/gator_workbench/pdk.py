"""Load ONE PDK so that the graph network understands every component in it (user request 2026-09-21).

Why this lives here and not in ``src/analog_optimizer``: the network is BUILT from a component list - device kinds,
terminal roles, parameter columns and their scales - that the package takes as an argument (``FeatureSchema``) and that
every saved model records in its contract. The package's own list (8 generic kinds, 8 parameters) is only its default.
A PDK list is therefore built here, from the PDK itself, and handed to the unchanged package: the source digest stays,
every model saved so far keeps its standard list and still loads, and the M6 audit re-runs unchanged. A model trained
with a PDK list loads only with that same list - the existing contract check says so.

What "Load PDK" reads (``bridge_read`` op ``pdk``), all read-only and at no simulation cost:

1. Virtuoso's own description of every cell of the technology library (its CDF): the Spectre name a cell netlists to,
   the pin order, the parameters written on each instance line, their declared units and defaults. A cell without a
   Spectre entry of its own (GPDK045's resistors) is looked into: its schematic places a primitive that names the model.
2. The PDK's Spectre model files, downloaded through the bridge into a temporary folder OUTSIDE the repository and
   deleted after scanning: which primitive each model is (``bsim4``, ``bjt``, ``diode``, ``resistor``...), its
   polarity, and which primitive terminal each pin reaches. PDK files are never copied; only the facts drawn from them
   and the files' SHA-256 are kept.
3. The ideal parts every circuit holds besides its PDK's - sources, ideal R / C / L, probes, controlled sources: the
   description of Cadence's generic library `analogLib`, in one more query that opens nothing (`IDEAL_SKILL`). Which
   Spectre component each of its cells netlists as, and in which pin order, is then read from Virtuoso like a PDK
   component's, not written by hand (user, 2026-10-05: "it should be recognizing all the loaded components").

Nothing is guessed from a name: a family comes from the Spectre primitive, a pin role from the primitive terminal the
pin reaches, a scale from the declared unit or else the PDK's own default value. What cannot be established stays
``unknown`` and is listed with the reason.

The component list covers the Spectre models that the library's cells netlist to. Models that no cell uses (internal
building blocks of the model files) are named in the record but not added.

How a circuit reaches the network (``Vocabulary.view``): the circuit graph of a task is left exactly as it is - the
environment, the backend, the replay and every table keep the graph the simulator saw. Only at the network's input,
each device whose Spectre model belongs to the PDK takes its PDK kind and pin roles, and its parameters are placed in
the PDK's columns. Devices outside the PDK (sources, ideal parts) keep their standard kinds.

Where each part lives (the refactoring of 2026-10-09, docs/plan-refactoring.md); every name stays reachable as
pdk.<name>:

- cdf_text: the CDF text the PDK read returns, form rules, numeric ranges, a parameter's CDF entry;
- model_scan: the model files read as text, each element's family and pin roles;
- pdk_record: the record built from both, the ideal parts of analogLib, the store of records (tests patch
  pdk_record.load_record and pdk_record.list_pdks, so code that must see such a patch reads them from pdk_record);
- vocabulary: the network's component list, the one a run keeps, the learner class it is built with;
- pdk_remote: the SKILL programs and the read out of Virtuoso, the model files kept per host.
"""
from __future__ import annotations


# re-exported: moved to cdf_text.py by the refactoring (docs/plan-refactoring.md)
from .cdf_text import (NUMERIC_CDF_TYPES, _fields, skill_value, _plist, _form_rule, numeric_range, parse_cdf_text,
                       _number, _REFERENCE, _cdf_entry, _write_source, _writable, _leaf_of)
# re-exported: the public names of six of them (refactoring package B9)
from .cdf_text import cdf_entry, cdf_number, leaf_of, query_fields, writability, write_source
# re-exported: moved to model_scan.py by the refactoring (docs/plan-refactoring.md)
from .model_scan import (CDF_UNITS, PASSIVE, PRIMITIVE_FAMILY, TERMINAL_ROLES, _ASSIGNMENT, _INCLUDE, _strip_comment,
                         _logical_lines, _assignments, includes_of, _define, scan_model_text, _spice_statement,
                         merge_scans, _where, _element_family, _paths, classify_model, pin_roles)
# re-exported: the public name of _where (refactoring package B9)
from .model_scan import file_line
# re-exported: moved to pdk_record.py by the refactoring (docs/plan-refactoring.md)
from .pdk_record import (FORMAT, VOCABULARY_FORMAT, STANDARD, NAME, REMOTE_PATH, MAX_MODEL_FILES, MAX_MODEL_BYTES,
                         PRIMITIVE_PINS, FAMILY_LABEL, UNIT_REFERENCE, ACTION_CLASS, SCALE_TOLERANCE_DECADES,
                         standard_schema, STANDARD_UNITS, IDEAL_LIBRARY, IDEAL_FORMAT, MAX_IDEAL_PINS, IDEAL_KINDS,
                         PdkError, build_record, _standard_roles, _decade, _compatible, _reference, _typical,
                         _assign_columns, _vocabulary, _summary, _pin_names, build_ideal_parts, _ideal_parts_of,
                         ideal_models, describe_ideal_parts, store_root, pdk_dir, save_record, load_record, list_pdks,
                         describe, label)
# re-exported: moved to vocabulary.py by the refactoring (docs/plan-refactoring.md)
from .vocabulary import (RUN_FILE, Vocabulary, current_vocabulary, learner_class, parameter_facts, parse_models,
                         requested, run_vocabulary, schema_label, vocabulary_of_record, write_run_vocabulary)
# re-exported: moved to pdk_remote.py by the refactoring (docs/plan-refactoring.md)
from .pdk_remote import (PDK_SKILL, pdk_skill, IDEAL_SKILL, ideal_skill, STAMP_SKILL, remote_stamps, ModelFileCache,
                         host_folder_name, read_from_virtuoso, read_ideal_parts, finish_load)


