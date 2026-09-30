"""Validated HTTP request bodies. Unknown fields remain errors."""
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field
from .. import ngspice_tasks
from .. import corner_check


PROFILE_ID = r'^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$'        # a connection profile: an identifier, never a host, port or command
CADENCE_NAME = r'^[A-Za-z_][A-Za-z0-9_.\-]{0,127}$'      # a Virtuoso library or cell
TASK_NAME = r'^[a-z][a-z0-9_]{1,39}$'                  # a saved task: real:<name>


class Body(BaseModel):
    model_config = ConfigDict(extra='forbid')          # hosts, ports, commands... simply do not exist as fields


class ConfigBody(Body):
    config: dict


class CircuitBody(Body):
    circuit: dict


class StartBody(Body):
    config: dict
    confirm_transfer: bool = False
    authorize_real_simulation: bool = False
    acknowledge_unknown_connection: bool = False
    baseline_only: bool = False


class CommandBody(Body):
    run_dir: str
    command: str = Field(pattern='^(pause|stop|cancel|checkpoint)$')       # checkpoint = "Save now": save and go on


class ContinueBody(Body):
    run_dir: str
    max_evaluations: int | None = Field(None, ge=1)
    authorize_real_simulation: bool = False
    acknowledge_unknown_connection: bool = False


class HintBody(Body):
    run_dir: str
    text: str = Field(min_length=1, max_length=1500)


class CornerCheckBody(Body):
    run_dir: str
    designs: int = Field(corner_check.MAX_DESIGNS, ge=1, le=corner_check.MAX_DESIGNS)
    expected_designs: list[str] | None = None        # the evaluations the page showed: a plan that changed is refused
    simulations: int | None = Field(None, ge=1)      # the number the page showed (and a real check's user authorized)
    authorize_real_simulation: bool = False
    acknowledge_unknown_connection: bool = False


class CornerStopBody(Body):
    run_dir: str
    check_id: str = Field(pattern=corner_check.CHECK_ID.pattern)


class PathBody(Body):
    path: str
    create: bool = False


class ConnectionBody(Body):
    profile_id: str = Field(pattern=PROFILE_ID)
    scope: str = Field('interactive', pattern='^(cheap|interactive|full)$')
    trigger: str = Field('user', pattern='^(user|auto)$')      # auto = profile change in the UI: cheap layers only


class ConnectBody(Body):
    profile_id: str = Field(pattern=PROFILE_ID)      # an identifier: never a host, port or command


class CreateConnectionBody(ConnectBody):
    """Identifiers only. `ssh_host` is a Host NAME that ~/.ssh/config of the backend user already holds (checked
    against that file by the backend); `bridge_profile` is a profile name of the bridge env file. Never an address."""
    kind: str = Field('virtuoso_ssh', pattern='^(virtuoso_ssh|virtuoso_local|ngspice_local|ngspice_ssh)$')
    ssh_host: str | None = Field(None, pattern=r'^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,63}$')
    bridge_profile: str | None = Field(None, pattern=r'^[A-Za-z0-9_]{1,32}$')


class NetworkSettingsBody(Body):
    network: dict | None = None         # hidden_dim / heads / layers
    advanced: dict | None = None        # the SAC numbers stored per encoder; any other key is rejected


class NetworkResetBody(Body):
    to: str = Field('publication', pattern='^(publication|gator_baseline)$')


class PdkLoadBody(Body):
    profile_id: str = Field(pattern=PROFILE_ID)
    technology_library: str | None = Field(None, pattern=r'^[A-Za-z_][A-Za-z0-9_.\-]{0,63}$')   # empty = the connection's design library's
    model_file: str | None = Field(None, max_length=1000)                                        # empty = the connection's model file


class NativeReadBody(Body):
    profile_id: str = Field(pattern=PROFILE_ID)
    library: str | None = None
    cell: str | None = None
    testbench: str | None = None        # import only: the cell whose netlist is exported (the testbench around `cell`)
    work_here: bool = False             # import only: the user said this cell is a copy they made - the task flow works in it (working_copy.declare)


class CopyBody(Body):
    profile_id: str | None = Field(None, pattern=PROFILE_ID)
    library: str = Field(pattern=CADENCE_NAME)
    cell: str = Field(pattern=CADENCE_NAME)


class SetupBody(CopyBody):
    config: dict | None = None          # the editors' rows, to say how the copy's setup differs from them


class TaskSaveBody(Body):
    profile_id: str | None = Field(None, pattern=PROFILE_ID)
    name: str = Field(pattern=TASK_NAME)
    config: dict
    library: str | None = Field(None, pattern=CADENCE_NAME)
    cell: str | None = Field(None, pattern=CADENCE_NAME)
    task: str | None = Field(None, pattern=TASK_NAME)     # the open task: updated, or the source of Save as
    as_new: bool = False
    extras: dict | None = None          # what the task file holds beside the rows: analyses, variables, bindings, frequency, notes


class TaskFileBody(Body):
    config: dict
    library: str | None = Field(None, pattern=CADENCE_NAME)
    cell: str | None = Field(None, pattern=CADENCE_NAME)
    task: str | None = Field(None, pattern=TASK_NAME)
    extras: dict | None = None


class TaskFileTextBody(Body):
    text: str = Field(max_length=2_000_000)


class TaskCheckBody(Body):
    profile_id: str | None = Field(None, pattern=PROFILE_ID)
    config: dict


class ProfileActionBody(Body):
    name: str = Field(pattern=TASK_NAME)
    run_dir: str | None = None


class NgspiceReadBody(Body):
    path: str = Field(min_length=1, max_length=1000)       # a file on the backend machine, inside an allowed input root


class NgspiceCheckBody(Body):
    text: str = Field(max_length=ngspice_tasks.MAX_NETLIST_BYTES)
    device_kinds: str | dict | None = None                  # "name=kind ..." as typed in the window, or a mapping
    source_path: str | None = Field(None, max_length=1000)  # where the deck was loaded from: its folder resolves relative includes


class NgspiceSaveBody(NgspiceCheckBody):
    name: str = Field(pattern=ngspice_tasks.NAME.pattern)
    circuit_class: str = Field('unspecified', max_length=120)
    pdk_id: str = Field('unspecified', max_length=200)


class NgspiceNameBody(Body):
    name: str = Field(pattern=ngspice_tasks.NAME.pattern)


class AgentSettingsBody(Body):
    provider: str
    model: str | None = None
    effort: str | None = None
    timeout_seconds: float | None = None      # IGNORED: a request has no time limit (7.48). Accepted because older pages send it
    permission_mode: str = 'dontAsk'
    allowed_tools: list[str] = []
    max_turns: int | None = None
    stream: bool = True


class ProposeBody(Body):
    kind: str
    prompt: str
    config: dict
    selection: list[dict] = []
    request_id: str | None = None
    web: bool = False                  # settings_review only: this ONE request may search the web and open publication sites
    run_dir: str | None = None         # run_review only: the run whose output the agent is given a digest of


class ImportBody(ProposeBody):
    result: dict | str


class ApproveBody(Body):
    proposal_id: str
    proposal_hash: str
    config: dict


class ApplyBody(Body):
    proposal_id: str
    config: dict


class DiffBody(Body):
    before: dict = {}
    after: dict = {}


class MatchedBody(Body):
    """Matched devices... (status record 7.103): the configuration, and - to see the change - the suggestions to make."""
    config: dict
    apply: list[str] | None = Field(None, max_length=500)


class CancelBody(Body):
    request_id: str


class RejectBody(Body):
    proposal_id: str


class ExportBody(Body):
    run_dir: str
    table: str | None = None


class ModelStructureBody(Body):
    run_dir: str
    checkpoint_id: str = Field('latest', max_length=120)


class GraphViewBody(ModelStructureBody):
    evaluation: int | None = Field(None, ge=1)      # which archived evaluation of that run; empty = the last one the save point had seen
