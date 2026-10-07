"""Metadata, settings, output roots and explicit connection actions."""
from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI, Query
from .. import __version__, bridge_connect, bridge_read, connection, directories, runs, schema, units
from .. import network_presets
from ..layout import environment_versions
from ..paths import PathNotAllowed, default_output_root, directory_bytes, repo_root
from ..storage.tables import TABLES, data_dictionary
from .models import (ConnectBody, ConnectionBody, CreateConnectionBody, DirectoriesBody, NetworkSettingsBody,
                     PROFILE_ID, PathBody, PdkLoadBody)
from .support import _bridge_call, fail
from .context import ApiContext


def register(app: FastAPI, context: ApiContext):
    @app.get('/api/meta')
    def meta():
        settings, settings_problem = runs.read_settings()      # a hand-edited file with a typo: said, not an HTTP 500
        return dict(version=__version__, repo_root=str(repo_root()), environment=environment_versions(),
                    default_output_root=str(default_output_root()), remembered=settings,
                    output_root=runs.remembered_output_root(), allowed_output_roots=[str(r) for r in context.roots.roots],
                    allowed_input_roots=[str(r) for r in context.input_roots],
                    produces='data, configurations, models, netlists and logs only - no plots, images or reports',
                    settings_problem=settings_problem,
                    # What this backend can do that an older one could not: the page sends request ids and asks the
                    # continuation check only where they are listed (record 7.261), so it works with either.
                    features=['launch_requests', 'continuation_check'])

    @app.get('/api/schema')
    def get_schema():
        return dict(schema_version=schema.CONFIG_SCHEMA_VERSION, json_schema=schema.json_schema(),
                    editors={name: schema.editor_columns(name) for name in schema.SECTIONS},
                    section_keys=schema.SECTION_KEYS, units=sorted(units._LOOKUP), unit_forms=units.written_forms(),
                    run_modes=schema.RUN_MODES,
                    encoder_types=schema.ENCODER_TYPES, tables=list(TABLES), data_dictionary=data_dictionary())

    @app.get('/api/network-settings')
    def network_settings():
        """What choosing an encoder loads: the operator's saved values, else the publication preset."""
        return network_presets.describe()

    @app.put('/api/network-settings/{encoder}')
    def save_network_settings(encoder: str, body: NetworkSettingsBody):
        """Editing a value in the panel stores it for THAT encoder. The whole value set is validated."""
        try:
            return network_presets.save(encoder, body.network, body.advanced)
        except KeyError:
            fail(404, f'Unknown encoder: {encoder}')
        except network_presets.InvalidNetworkSettings as exc:
            fail(422, exc)

    @app.get('/api/pdks')
    def loaded_pdks():
        """The PDKs loaded so far (local files only). Each one can be the network's component list."""
        from .. import pdk
        return dict(pdks=pdk.list_pdks(), standard=dict(vocabulary=pdk.STANDARD, label=pdk.label(None),
                                                         kinds=list(pdk.standard_schema().device_kinds),
                                                         parameters=list(pdk.standard_schema().parameters)))

    @app.get('/api/pdks/{pdk_id}')
    def loaded_pdk(pdk_id: str):
        """Everything that was read about one loaded PDK: every component, its pins and roles, its parameters."""
        from .. import pdk
        record = pdk.load_record(pdk_id)
        if record is None:
            fail(404, f'PDK {pdk_id} is not loaded')
        return pdk.describe(record)

    @app.post('/api/pdks/load')
    def load_pdk(body: PdkLoadBody):
        """Explicit click: read one technology library's own description and its Spectre model files through the
        connection (read-only, no simulation), and store what the network needs. PDK files are not kept."""
        return _bridge_call(lambda: bridge_read.read(context.monitor, body.profile_id, 'pdk', library=body.technology_library or None,
                                                     model_file=body.model_file or None))          # a PdkError is a ValueError: 422

    @app.get('/api/output/browse')
    def output_browse(path: str | None = None):
        try:
            return context.roots.browse(path)
        except PathNotAllowed as exc:
            fail(403, exc)

    @app.post('/api/output/check')
    def output_check(body: PathBody):
        result = context.roots.check(body.path, create=body.create)
        if result['allowed'] and result['resolved']:
            result['mock_data_root'] = str(Path(result['resolved']) / 'mock')
            result['bytes_used'] = (directory_bytes(result['resolved']) if Path(result['resolved']).is_dir() else 0) if body.usage else None
        return result

    @app.get('/api/connection/profiles')
    def connection_profiles():
        return connection.public_profiles()

    @app.get('/api/connection/status')
    def connection_status(profile_id: str = Query(pattern=PROFILE_ID)):
        return bridge_connect.describe(context.monitor.status(profile_id))

    @app.post('/api/connection/check')
    def connection_check(body: ConnectionBody):
        """Read-only and zero-cost; never a baseline simulation. trigger=auto (profile change) is limited
        to the cheap layers by the monitor itself. The answer carries a one-sentence `summary` and, once the
        tunnel layer is known, the `ciw` line to load in Virtuoso."""
        try:
            return bridge_connect.describe(context.monitor.check(body.profile_id, scope=body.scope, trigger=body.trigger))
        except ValueError as exc:
            fail(422, exc)

    @app.get('/api/connection/setup')
    def connection_setup():
        """What "Create connection" would use, per kind of connection: the bridge setup, the ngspice and ssh programs
        and the Host NAMES of ~/.ssh/config found on THIS host. Locates and names; contacts nothing."""
        return bridge_connect.detect_setup()

    @app.post('/api/connection/profile')
    def connection_create_profile(body: CreateConnectionBody):
        """Explicit click. The browser names the new connection and its kind; every path comes from this host and
        an ssh machine only by a Host name this host already holds. Existing connections are operator-owned and are
        never changed: a new one is added next to them, the previous file is kept as a copy."""
        try:
            created = bridge_connect.create_profile(body.profile_id, kind=body.kind, ssh_host=body.ssh_host,
                                                    bridge_profile=body.bridge_profile)
        except bridge_connect.ProfileExists as exc:
            fail(409, exc, code='profile_exists')
        except FileExistsError as exc:
            fail(409, exc, code='connection_file_unreadable')
        except bridge_connect.SetupNotFound as exc:
            fail(409, exc, code=exc.reason_code)
        except ValueError as exc:
            fail(422, exc)
        return dict(created, profiles=connection.public_profiles())

    @app.get('/api/connection/directories')
    def connection_directories():
        """The folders outside the repository that the simulator connection uses (record 7.168): each one's default,
        the value in use and where it comes from (the environment, the connection file or the default)."""
        return directories.describe()

    @app.put('/api/connection/directories')
    def save_connection_directories(body: DirectoriesBody):
        """Explicit click on "Save folders": every changed folder is checked (one on this machine that GATOR writes into
        is made and written once), then the connection file's "directories" block is written with the previous file
        kept as a copy. The connections themselves are never changed here."""
        try:
            return bridge_connect.save_directories(body.values)
        except FileExistsError as exc:
            fail(409, exc, code='connection_file_unreadable')
        except bridge_connect.FolderBusy as exc:
            fail(409, exc, code='folder_busy')
        except directories.InvalidDirectory as exc:
            fail(422, exc, code='invalid_folder', folder=exc.key)

    @app.post('/api/connection/connect')
    def connection_connect(body: ConnectBody):
        """Explicit click: start the SSH tunnel of a configured Virtuoso profile (as `virtuoso-bridge start` does; for
        Virtuoso on this machine it sets the local bridge up instead) and report the line to load in the CIW. A
        running tunnel is left untouched; nothing is ever stopped or restarted. Followed by the CHEAP check (no
        Virtuoso contact) so the indicator shows the new state. An ngspice connection has nothing to start."""
        try:
            settings = connection.resolve_profile_id(body.profile_id)
        except KeyError:
            fail(404, 'Unknown connection profile', code='profile_not_configured')
        if connection.family_of(connection.profile_kind(settings)) == 'ngspice':
            fail(409, bridge_connect.NEXT_STEPS['nothing_to_connect'], code='nothing_to_connect')
        result = context.connector.connect(body.profile_id)
        return dict(connect=result, status=bridge_connect.describe(context.monitor.check(body.profile_id, scope='cheap', trigger='user')))
