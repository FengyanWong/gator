"""Validated HTTP request bodies. Unknown fields remain errors."""
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field
from .. import ngspice_tasks
from .. import corner_check
from ..calibration import MAX_DESIGNS
from ..launch_requests import ID_PATTERN as LAUNCH_REQUEST_ID


from ..names import CADENCE_NAME, PROFILE_ID, TASK_NAME   # the patterns of a Virtuoso name, a connection, a task

_MAX_PATH_CHARS = 1000



# Shared request-body contract that rejects unknown fields.
class Body(BaseModel):
    model_config = ConfigDict(extra='forbid')          # hosts, ports, commands... simply do not exist as fields


# A raw configuration dictionary carried by configuration-oriented endpoints.
class ConfigBody(Body):
    config: dict


# Configuration validation input with the optional saved revision from which the editor rows were loaded.
class ValidateBody(ConfigBody):
    rows_from: int | None = Field(None, ge=1)     # the saved revision the page's rows came from, when it knows (record 7.203)


# Circuit selection payload validated by the circuit-loading endpoint.
class CircuitBody(Body):
    circuit: dict


# Run configuration, launch identity and explicit execution acknowledgements for starting a run.
class StartBody(Body):
    config: dict
    confirm_transfer: bool = False
    authorize_real_simulation: bool = False
    acknowledge_unknown_connection: bool = False
    baseline_only: bool = False
    calibration_only: bool = False
    # With baseline_only: this many random designs after the baseline, for the calibration (calibration.py). 0 = none.
    calibration_designs: int = Field(0, ge=0, le=MAX_DESIGNS)
    # The page's id for this launch (record 7.261): the same id again gets the run the first request made.
    request_id: str | None = Field(None, pattern=LAUNCH_REQUEST_ID)


# Run directory and a supported control or save-point command.
class CommandBody(Body):
    run_dir: str
    command: str = Field(pattern='^(pause|stop|cancel|checkpoint)$')       # checkpoint = "Save now": save and go on


# Run directory, optional evaluation limit and acknowledgements for resuming a run.
class ContinueBody(Body):
    run_dir: str
    max_evaluations: int | None = Field(None, ge=1)
    authorize_real_simulation: bool = False
    acknowledge_unknown_connection: bool = False
    request_id: str | None = Field(None, pattern=LAUNCH_REQUEST_ID)       # as for StartBody (record 7.261)


# Budgeted corner-check request naming the run and any previously previewed designs.
class CornerCheckBody(Body):
    run_dir: str
    designs: int = Field(corner_check.MAX_DESIGNS, ge=1, le=corner_check.MAX_DESIGNS)
    expected_designs: list[str] | None = None        # the evaluations the page showed: a plan that changed is refused
    simulations: int | None = Field(None, ge=1)      # the number the page showed (and a real check's user authorized)
    authorize_real_simulation: bool = False
    acknowledge_unknown_connection: bool = False


# Run and check identities for stopping one corner check.
class CornerStopBody(Body):
    run_dir: str
    check_id: str = Field(pattern=corner_check.CHECK_ID.pattern)


# Backend output path with explicit directory-creation and usage-measurement options.
class PathBody(Body):
    path: str
    create: bool = False
    # The folder's size is walked only when asked (record 7.189): on D: the walk took 0.7 to 2 s, on every page open, for
    # one number inside a closed fold; the page asks for it with its "Measure" button.
    usage: bool = False


# Configured connection identity with the requested check scope and trigger.
class ConnectionBody(Body):
    profile_id: str = Field(pattern=PROFILE_ID)
    scope: str = Field('interactive', pattern='^(cheap|interactive|full)$')
    trigger: str = Field('user', pattern='^(user|auto)$')      # auto = profile change in the UI: cheap layers only


# Configured connection identity used for connection lifecycle actions.
class ConnectBody(Body):
    profile_id: str = Field(pattern=PROFILE_ID)      # an identifier: never a host, port or command


class CreateConnectionBody(ConnectBody):
    """Identifiers only. `ssh_host` is a Host NAME that ~/.ssh/config of the backend user already holds (checked
    against that file by the backend); `bridge_profile` is a profile name of the bridge env file. Never an address."""
    kind: str = Field('virtuoso_ssh', pattern='^(virtuoso_ssh|virtuoso_local|ngspice_local|ngspice_ssh)$')
    ssh_host: str | None = Field(None, pattern=r'^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,63}$')
    bridge_profile: str | None = Field(None, pattern=r'^[A-Za-z0-9_]{1,32}$')


class DirectoriesBody(Body):
    """The folders of the connection module (record 7.168): {folder name: path, or null for its default}. Checked one by
    one by `directories.normalized` and, for a folder on this machine, by writing into it."""
    values: dict[str, str | None]


# Remembered network dimensions and per-encoder SAC settings supplied by the page.
class NetworkSettingsBody(Body):
    network: dict | None = None         # hidden_dim / heads / layers
    advanced: dict | None = None        # the SAC numbers stored per encoder; any other key is rejected


# Connection identity and optional technology or model overrides for loading a PDK record.
class PdkLoadBody(Body):
    profile_id: str = Field(pattern=PROFILE_ID)
    technology_library: str | None = Field(None, pattern=r'^[A-Za-z_][A-Za-z0-9_.\-]{0,63}$')   # empty = the connection's design library's
    model_file: str | None = Field(None, max_length=_MAX_PATH_CHARS)                                        # empty = the connection's model file


# Connection and cell selection for browsing, reading or importing a native circuit.
class NativeReadBody(Body):
    profile_id: str = Field(pattern=PROFILE_ID)
    library: str | None = None
    cell: str | None = None
    testbench: str | None = None        # import only: the cell whose netlist is exported (the testbench around `cell`)
    work_here: bool = False             # import only: the user said this cell is a copy they made - the task flow works in it (working_copy.declare)


# Library and cell selection with an optional configured connection for working-copy operations.
class CopyBody(Body):
    profile_id: str | None = Field(None, pattern=PROFILE_ID)
    library: str = Field(pattern=CADENCE_NAME)
    cell: str = Field(pattern=CADENCE_NAME)


# Working-copy selection plus optional editor rows for comparing its Maestro setup.
class SetupBody(CopyBody):
    config: dict | None = None          # the editors' rows, to say how the copy's setup differs from them


# Saved-task payload with circuit rows, optional setup extras and revision-conflict choices.
class TaskSaveBody(Body):
    profile_id: str | None = Field(None, pattern=PROFILE_ID)
    name: str = Field(pattern=TASK_NAME)
    config: dict
    library: str | None = Field(None, pattern=CADENCE_NAME)
    cell: str | None = Field(None, pattern=CADENCE_NAME)
    task: str | None = Field(None, pattern=TASK_NAME)     # the open task: updated, or the source of Save as
    as_new: bool = False
    extras: dict | None = None          # what the task file holds beside the rows: analyses, variables, bindings, frequency, notes
    base_revision: int | None = Field(None, ge=1)   # the saved revision the rows came from, when the page knows (record 7.203)
    replace_newer: bool = False         # the user answered "Save anyway": rows older than the saved task may replace it


# Circuit rows and optional task identity and setup extras used to build a task file.
class TaskFileBody(Body):
    config: dict
    library: str | None = Field(None, pattern=CADENCE_NAME)
    cell: str | None = Field(None, pattern=CADENCE_NAME)
    task: str | None = Field(None, pattern=TASK_NAME)
    extras: dict | None = None


# Saved-task identity and optional connection and output-root choices for a baseline run.
class TaskBaselineBody(Body):
    task_key: str
    profile_id: str | None = Field(None, pattern=PROFILE_ID)
    output_root: str | None = None


# Bounded task-file text submitted for parsing.
class TaskFileTextBody(Body):
    text: str = Field(max_length=2_000_000)


# Configuration and optional connection used for a saved-task consistency check.
class TaskCheckBody(Body):
    profile_id: str | None = Field(None, pattern=PROFILE_ID)
    config: dict


# Saved-profile name and optional run directory used by profile actions.
class ProfileActionBody(Body):
    name: str = Field(pattern=TASK_NAME)
    run_dir: str | None = None


# Backend path submitted for reading an ngspice deck.
class NgspiceReadBody(Body):
    path: str = Field(min_length=1, max_length=_MAX_PATH_CHARS)       # a file on the backend machine, inside an allowed input root


# ngspice deck text, device-kind hints and source location used for import checks.
class NgspiceCheckBody(Body):
    text: str = Field(max_length=ngspice_tasks.MAX_NETLIST_BYTES)
    device_kinds: str | dict | None = None                  # "name=kind ..." as typed in the window, or a mapping
    source_path: str | None = Field(None, max_length=_MAX_PATH_CHARS)  # where the deck was loaded from: its folder resolves relative includes


# ngspice deck input with saved-task labels and connection or output choices.
class NgspiceSaveBody(NgspiceCheckBody):
    name: str = Field(pattern=ngspice_tasks.NAME.pattern)
    circuit_class: str = Field('unspecified', max_length=120)
    pdk_id: str = Field('unspecified', max_length=200)
    profile_id: str | None = Field(None, pattern=PROFILE_ID)
    output_root: str | None = None


# Name identifying a saved ngspice task.
class NgspiceNameBody(Body):
    name: str = Field(pattern=ngspice_tasks.NAME.pattern)


class OpenCliBody(Body):
    """The Agent window's buttons: which CLI to open. Nothing else: the folder, the window and how the CLI starts are fixed."""
    cli: str = Field(pattern='^(claude|codex)$')


# Before and after configuration dictionaries for a structured comparison.
class DiffBody(Body):
    before: dict = {}
    after: dict = {}


class MatchedBody(Body):
    """Matched devices... (status record 7.103): the configuration, and - to see the change - the suggestions to make."""
    config: dict
    apply: list[str] | None = Field(None, max_length=500)


# Run directory and optional table selection for saved-data exports.
class ExportBody(Body):
    run_dir: str
    table: str | None = None


# Run and save-point selection used to inspect a saved model network.
class ModelStructureBody(Body):
    run_dir: str
    checkpoint_id: str = Field('latest', max_length=120)


class RenameTaskBody(Body):
    """The name a task is shown under from now on (record 7.302). Its key stays."""
    task_key: str = Field(min_length=3, max_length=200)
    name: str = Field(max_length=200)               # the route says the real rule in plain words


class RenameModelBody(Body):
    """A saved model's new name (record 7.225)."""
    run_dir: str
    model_label: str = Field(max_length=200)        # the route says the real limit (80) in plain words


# Saved-model selection with an optional archived evaluation for graph inspection.
class GraphViewBody(ModelStructureBody):
    evaluation: int | None = Field(None, ge=1)      # which archived evaluation of that run; empty = the last one the save point had seen
