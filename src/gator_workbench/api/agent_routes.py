"""Agent proposals, streaming replies, review and scoped tool sessions."""
from __future__ import annotations
import secrets
from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError
from .. import agents, bridge_read, runs, schema
from .. import profiles, recipes, virtuoso_setup, working_copy
from ..agents import AgentError, AgentRequest, AgentSettings, ProposalRejected
from ..agents import catalog as agent_catalog
from ..agents import proposals as agent_proposals
from ..agents import run_digest as agent_run_digest
from ..agents import settings_review as agent_review
from ..agents import diagnostics as agent_diagnostics
from ..agents import tools as agent_tool_catalog
from ..agents.prompts import circuit_summary
from ..paths import append_local_log
from ..security import redact
from ..storage.dataset import utcnow
from .models import AgentSettingsBody, ApplyBody, ApproveBody, CancelBody, ConfigBody, ImportBody, ProposeBody, RejectBody
from .support import agent_settings, fail, live_answer, load_runtime, validate_loaded
from .context import ApiContext


def register(app: FastAPI, context: ApiContext):
    @app.get('/api/agent/diagnostics')
    def diagnostics():
        return dict(agent_diagnostics.diagnose(), availability=agents.availability(), selected=agent_settings().provider)

    @app.get('/api/agent/settings')
    def get_agent_settings():
        settings = agent_settings()
        return dict(vars(settings), allowed_tools=list(settings.allowed_tools), availability=agents.availability(),
                    catalog=agent_catalog.for_api(),        # static table + one local file read: no CLI, no model call
                    note='Agent model, effort and tools are independent of RL checkpoints, simulator '
                         'concurrency and evaluation budgets. A request has no time limit; "Cancel request" stops it.')

    @app.put('/api/agent/settings')
    def put_agent_settings(body: AgentSettingsBody):
        try:
            settings = AgentSettings(**dict(body.model_dump(exclude={'timeout_seconds'}), allowed_tools=tuple(body.allowed_tools))).validate()
            agents.make_provider(settings)
        except AgentError as exc:
            raise HTTPException(422, detail=exc.as_dict())
        saved = dict(vars(settings), allowed_tools=list(settings.allowed_tools))
        saved.pop('timeout_seconds')
        runs.save_settings(agent=saved)
        return dict(saved=True, provider=settings.provider)

    def check_suggestions(request, proposal):
        """Every suggested setting is tried on a COPY of the configuration - schema, then static validation with the loaded
        circuit - so the user sees which rows are legal before applying one. Nothing is applied here."""
        if request.kind not in ('settings_review', 'run_review'):
            return
        runtime, _ = load_runtime(context.parse_config(request.config))

        def validate_config(raw):
            try:
                parsed = schema.WorkbenchConfig.model_validate(raw)
            except ValidationError as exc:
                return '; '.join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:3]), []
            report = validate_loaded(parsed, runtime)
            return None, [issue.code for issue in report.issues if issue.level in ('error', 'blocker')]
        checked = agent_review.check(request.config, proposal['suggestions'], validate_config=validate_config)
        proposal['suggestions'], proposal['suggestions_together'] = checked['suggestions'], checked['all_together']

    def readiness_after(request, proposal):
        """Would the run start once this proposal is applied? The backend's own answer on the patched configuration -
        never the agent's claim. None when it cannot be worked out (the proposal itself is unaffected)."""
        try:
            patched, runtime, blocked = context.load_config(
                agent_proposals.apply_patch(request.config, proposal['patch'], selection=request.selection))
            after = context.run_readiness(patched, runtime, blocked)
        except Exception:
            return None
        state = {item['id']: item['status'] for item in after['items']}
        was_missing = [item for item in (request.readiness or {}).get('items', []) if item['status'] == 'missing' and item['id'] != 'start']
        return dict(ready=after['ready'], changed_rows=len(proposal['diff']),
                    resolved=[item['title'] for item in was_missing if state.get(item['id']) != 'missing'],
                    remaining=[dict(title=item['title'], who=item['who'], detail=item['detail'], action=item['action'])
                               for item in after['items'] if item['status'] == 'missing' and item['id'] != 'start'],
                    note='Worked out by the backend on the configuration as it would be after approval.')

    def _request(body) -> tuple:
        config, runtime, blocked = context.load_config(body.config)
        summary = None if runtime is None else circuit_summary(runtime.base_graph, circuit=runtime.circuit)
        if summary is not None and not runtime.mock:
            # A real backend produces a fixed set of results per circuit type, and writes what the property form lets a user
            # type. Said to the agent, so its measurement rows name results that exist and its variables can be written.
            if runtime.circuit.get('native_draft'):
                summary['results_by_circuit_type'] = {key: list(recipes.provided_metrics(key)) for key in profiles.RECIPES}
                summary['real_backend_limits'] = (
                    'This cell has no circuit profile yet. When one is created from your proposal: a measurement with '
                    'result_source "backend_profile" must use a source_name from results_by_circuit_type for the fitting circuit '
                    'type; a parameter can be optimized when the property form of its instance (directly inside the core cell) '
                    'lets a user type it - transistor w, l, nf, m, a MIM capacitor\'s w, l, m, ... (a form that greys a field out '
                    'or computes it, e.g. areas, refuses it) - lengths on a 5 nm grid, counts in whole numbers, and a range that '
                    'contains the present value; a transistor varies its total width or its finger count, not both. Identical or '
                    'matched parts should follow one leader through binding_group with ratio 1. A target\'s metric_id must be '
                    'one of those result names too (the profile registers exactly them for the optimizer).')
            else:
                summary['results_provided'] = list(runtime.provided_metrics)
            if runtime.reference_metrics:
                # Verified REAL results of the design AS IT STANDS (its recorded baseline). The only numbers a PROVISIONAL
                # "no worse than the initial design" target may be built from; nothing here is a requirement of the user.
                summary['initial_design_results'] = runtime.reference_metrics
        circuit_hash = None if runtime is None else runtime.circuit.get('netlist_sha256')
        ready, review = context.run_readiness(config, runtime, blocked), None
        if body.kind == 'settings_review':
            # Settings, cited presets and a digest of the task - and nothing of the design (no instance, net or size), so a
            # request that may read web pages has nothing of it to give away.
            raw = config.model_dump(mode='json')
            review = dict(task=agent_review.task_digest(raw, summary), settings=agent_review.settings_data(raw),
                          publication_presets=agent_review.publication_presets(), run_readiness=agent_review.readiness_digest(ready))
            summary = None
        results = None
        if body.kind == 'run_review':
            if not body.run_dir:
                raise AgentError('invalid_request', 'A run_review needs a run: choose one with "Runs..." first')
            # The agent reads no file: the backend condenses the run's own records. `run_path` keeps it inside the allowed roots.
            results = agent_run_digest.load(context.run_path(body.run_dir))
            review = dict(settings=agent_review.settings_data(config.model_dump(mode='json')))      # so a suggestion names a real setting
        copy = None
        if body.kind in ('virtuoso_setup', 'virtuoso_work'):
            # The working copy the setup is for, given as DATA: its names, what the workbench last wrote into its Maestro
            # test, which values may be variables, and the only calculator functions an output may call. A `virtuoso_work`
            # request can read all of this again through its tools; it is here so the first turn already knows it.
            try:
                target = _setup_target(config)
            except working_copy.CopyError as exc:
                raise AgentError('invalid_request', str(exc))
            own = working_copy.is_declared(target)          # the user's own copy, declared on the read: written directly
            copy = dict(copy=target['copy'], cell_you_drew=None if own else target['original'], own_copy=own, test=virtuoso_setup.TEST,
                        maestro_now=working_copy.last_written(target) or 'nothing written by the workbench yet',
                        bindable=[dict(cell=c, instance=i, parameters=sorted(p)) for (c, i), p in sorted(working_copy.bindable_on(target).items())],
                        allowed_functions=sorted(virtuoso_setup.FUNCTIONS),
                        model_files=working_copy.default_model_files(config.run.connection_profile_id),
                        note=('This is the cell the user declared as a copy they made; the workbench writes into it directly. ' if own else '')
                             + 'The circuit data is read from the copy\'s cell; instance paths and nets are the same in the copy.')
        request = AgentRequest(kind=body.kind, user_prompt=body.prompt, config=config.model_dump(mode='json'),
                               circuit_summary=summary, selection=body.selection, readiness=ready, review=review, results=results,
                               web=bool(body.web), web_domains=agent_review.domains(runs.load_settings().get('agent_web_domains')),
                               copy=copy)
        if body.request_id:
            request.request_id = body.request_id
        return request, circuit_hash

    @app.post('/api/agent/propose')
    def propose(body: ProposeBody, http: Request):
        """Proposal only. Applying needs approval; circuit writes and simulations need their own authorization.
        A request that accepts `text/event-stream` gets the answer LIVE (`live_answer`), any other gets it in one piece.
        A request of a TOOL kind (agents/tools.py) also gets the workbench's Virtuoso tools for as long as it runs."""
        session = None
        try:
            request, circuit_hash = _request(body)
            provider = agents.make_provider(agent_settings())
            # Validated BEFORE the tools are opened: a request that cannot be sent used to leave the live-answer path with
            # an open tool session (its token still worked), because only the plain path had the `finally` that closes it.
            request.validate()
            if request.kind in agents.TOOL_KINDS and not getattr(provider, 'carries_tools', False):
                fail(409, f'The {settings_provider_name(provider)} provider cannot be given the workbench\'s Virtuoso tools, '
                          f'so a "{request.kind}" request would work without them and say it has them. Choose the Claude Code '
                          'provider under Agent settings, or a request kind that needs no tools.', code='tools_unsupported')
            session = _open_tools(request, context.parse_config(body.config), http)

            def finish(result):
                proposal = _proposal(request, result, circuit_hash, session)
                _audit(proposal)
                return proposal

            def done():
                if session is not None:
                    _close_tools(session)
            if 'text/event-stream' in http.headers.get('accept', ''):
                return live_answer(request, provider, finish, done=done, outcome=lambda: _tool_outcome(session))
            try:
                return finish(provider.propose(request))
            finally:
                done()
        except AgentError as exc:
            # A request that FAILS may already have written the working copy through its tools. Saying only
            # "configuration_unchanged" read as "nothing happened" (review of 2026-09-23): the tables are unchanged, the
            # copy in Virtuoso is not, and the answer now says which tools ran and whether one of them wrote.
            raise HTTPException(409, detail=dict(exc.as_dict(), configuration_unchanged=True, **_tool_outcome(session)))

    def _proposal(request, result, circuit_hash, session=None):
        """A reply - the agent's, or one imported by hand (no tools, so no `tool_calls`) - as a proposal: a Virtuoso setup
        checked for writability, what its tools did, whether the run would start after it, its suggestions tried."""
        proposal = context.proposals.create(request, result, circuit_hash=circuit_hash)
        if request.kind == 'virtuoso_setup':
            check_setup(request, proposal)
        proposal.update(_tool_outcome(session))
        proposal['readiness_after'] = readiness_after(request, proposal)
        check_suggestions(request, proposal)
        return proposal

    def _open_tools(request, config, http):
        """Open this request's tools, if its kind has any. The session holds what the agent may not choose: the working
        copy (resolved from the configuration, never from a tool argument), the connection it goes through, and how many
        calls are left. It is closed when the request ends, and its token stops working with it."""
        names = agent_tool_catalog.granted(request.kind)
        if not names:
            return None
        profile_id = config.run.connection_profile_id
        session = agent_tool_catalog.ToolSession(
            request_id=request.request_id, token=secrets.token_urlsafe(32), kind=request.kind, monitor=context.monitor,
            profile_id=profile_id, names=tuple(names), on_call=_tool_record,
            target=lambda: _setup_target(config),
            read=lambda op, **wanted: bridge_read.read(context.monitor, profile_id, op, **wanted))
        context.tool_sessions[session.token] = session
        request.tools = tuple(names)
        request.tools_url = str(http.base_url).rstrip('/')
        request.tools_token = session.token
        return session

    def _close_tools(session):
        session.close()
        context.tool_sessions.pop(session.token, None)

    def _tool_outcome(session) -> dict:
        """What this request's tools did - said with the answer AND with a failure, because a request that ends badly may
        already have written the working copy."""
        if session is None:
            return {}
        return dict(tool_calls=[dict(tool=c['tool'], ok=c['ok'], error=c['error']) for c in session.history],
                    virtuoso_copy_written=session.wrote)

    def settings_provider_name(provider) -> str:
        return getattr(provider, 'name', None) or type(provider).__name__

    def _log_line(file, note, /, **entry):          # positional-only: an entry may carry any key
        """One line of a local agent log. A log that cannot be written never fails the request or its tool call."""
        append_local_log(file, lambda: dict(time_utc=utcnow().isoformat(), **entry, note=note))

    def _tool_record(entry):
        _log_line('agent_tool_calls.jsonl', "One workbench tool call of an agent request: a read, or a Maestro setup written "
                                            "into a working copy. Never the user's own cell, never a simulation.", **entry)

    @app.post('/api/agent/tools')
    def agent_tools(body: dict):
        """Where the tool server of ONE running request (gator_workbench/agent_tools.py) asks. The token says which
        request it belongs to; a request that has ended has no tools, and nothing else is accepted."""
        session = context.tool_sessions.get(str(body.get('token') or ''))
        if session is None or session.closed:
            raise HTTPException(403, detail='These tools are closed: the agent request they belong to is over.')
        if body.get('method') == 'list':
            return dict(tools=agent_tool_catalog.described(session.names))
        if body.get('method') != 'call':
            raise HTTPException(422, detail=f'Unknown tool method {body.get("method")!r}')
        return session.call(str(body.get('name') or ''), body.get('arguments') or {})

    def _setup_target(config):
        """The working copy a Virtuoso setup is about: the cell's own copy (Circuit source: Virtuoso) or an open task's copy."""
        circuit = config.circuit
        if circuit.source == 'virtuoso' and circuit.library and circuit.cell:
            return working_copy.draft_target(circuit.library, circuit.cell)
        if circuit.source == 'registered_task' and (circuit.task_id or '').startswith('real:'):
            entry = profiles.list_profiles().get(circuit.task_id[len('real:'):])
            if entry and entry.get('copy_target'):
                return entry['copy_target']
        raise working_copy.CopyError('Setting up in Virtuoso needs the cell the task flow works in: read the cell into the workbench '
                                     'and confirm that it is a copy you made (the Virtuoso window asks); a task saved with Save task has one')

    def _setup_of(config, proposal):
        setup = proposal.get('setup') or {}
        return virtuoso_setup.from_rows(config, analyses=setup.get('analyses'), variables=setup.get('variables'),
                                        bindings=setup.get('bindings'), initial_conditions=setup.get('initial_conditions'))

    def check_setup(request, proposal):
        """A proposed Virtuoso setup must be writable as it stands: only allowed calculator functions, variables only on
        values nothing is computed from, every output with the analysis it reads. Otherwise the proposal is refused here -
        before anyone can approve it - with the reasons."""
        preview = schema.WorkbenchConfig.model_validate(agent_proposals.apply_patch(request.config, proposal['patch']))
        target = _setup_target(preview)
        wanted = _setup_of(preview, proposal)
        problems = virtuoso_setup.validate(wanted, bindable=working_copy.bindable_on(target))
        if wanted['analyses'] is not None:
            read = {m.analysis for m in preview.measurements if m.result_source == 'ade_output' and m.analysis != 'other'}
            missing = sorted(read - set(wanted['analyses']))
            if missing:
                problems.append(f'Outputs read the analyses {", ".join(missing)}, which setup.analyses does not set')
        if problems:
            context.proposals.reject(proposal['proposal_id'])
            raise AgentError('schema_failure', 'The proposed Virtuoso setup was refused by the backend: ' + '; '.join(problems)[:3000],
                             problems=problems)
        proposal['virtuoso_copy'] = target['copy']

    @app.post('/api/agent/readiness')
    def readiness(body: ConfigBody):
        """What is still missing before this run can start. Computed here: no agent is called and nothing is probed."""
        config, runtime, blocked = context.load_config(body.config)
        return context.run_readiness(config, runtime, blocked)

    @app.post('/api/agent/cancel')
    def cancel(body: CancelBody):
        return dict(cancelled=agents.REGISTRY.cancel(body.request_id))

    @app.post('/api/agent/export-task')
    def export_task(body: ProposeBody):
        try:
            request, _ = _request(body)
            return agents.DisabledProvider().export_task(request)
        except AgentError as exc:
            raise HTTPException(422, detail=exc.as_dict())

    @app.post('/api/agent/import-result')
    def import_result(body: ImportBody):
        try:
            request, circuit_hash = _request(body)
            return _proposal(request, agents.DisabledProvider().import_result(request, body.result), circuit_hash)
        except AgentError as exc:
            raise HTTPException(409, detail=dict(exc.as_dict(), configuration_unchanged=True))

    def _circuit_hash(config):
        runtime, _ = load_runtime(config)
        return None if runtime is None else runtime.circuit.get('netlist_sha256')

    def _proposal_call(action, **refused):
        """A call on the proposal store: an unknown proposal is a 404, a refused one a 409 that says why."""
        try:
            return action()
        except KeyError:
            fail(404, 'Unknown proposal')
        except ProposalRejected as exc:
            raise HTTPException(409, detail=dict(message=str(exc), problems=exc.problems, **refused))

    @app.post('/api/agent/approve')
    def approve(body: ApproveBody):
        config = context.parse_config(body.config)
        return _proposal_call(lambda: context.proposals.approve(body.proposal_id, proposal_hash=body.proposal_hash,
                                                                config=config.model_dump(mode='json'), circuit_hash=_circuit_hash(config)))

    @app.post('/api/agent/apply')
    def apply(body: ApplyBody):
        config = context.parse_config(body.config)
        updated = _proposal_call(lambda: context.proposals.apply(body.proposal_id, config=config.model_dump(mode='json'),
                                                                 circuit_hash=_circuit_hash(config)), configuration_unchanged=True)
        new_config = context.parse_config(updated)
        runtime, _ = load_runtime(new_config)
        report = validate_loaded(new_config, runtime)
        proposal = context.proposals.get(body.proposal_id)
        if proposal['kind'] != 'virtuoso_setup':
            return dict(config=updated, validation=report.as_dict(),
                        note='Configuration only. No circuit was written and no simulation was started.')
        # The approved setup goes into the WORKING COPY - never the user's cell - and is read back. The rows are applied
        # either way; if Virtuoso cannot be reached, Save task does the rest later (the page keeps the approved setup for
        # it - the separate "Write to Virtuoso" button went on 2026-09-22).
        virtuoso, profile_id = None, new_config.run.connection_profile_id
        try:
            if not profile_id:
                raise working_copy.CopyError('No connection is chosen: choose one in the Connection window')
            target = _setup_target(new_config)
            written = working_copy.write_setup_on(context.monitor, profile_id, target, _setup_of(new_config, proposal))
            virtuoso = dict(written=True, matches=written['matches'], differences=written['differences'], copy=target['copy'])
        except PermissionError as exc:
            virtuoso = dict(written=False, error=str(exc), gate=getattr(exc, 'gate', None))
        except (working_copy.CopyError, virtuoso_setup.SetupError) as exc:
            virtuoso = dict(written=False, error=str(exc))
        except Exception as exc:
            virtuoso = dict(written=False, error=redact(f'{type(exc).__name__}: {exc}', 600))
        if virtuoso['written']:
            note = (f"The rows were applied and the setup was written into the working copy {target['copy']['library']}/"
                    f"{target['copy']['testbench']} (not your cell), then read back: "
                    + ('it matches.' if virtuoso['matches'] else 'it differs - see the differences.') + ' No simulation was started.')
        else:
            note = (f"The rows were applied; writing into the working copy failed: {virtuoso['error']} Once Virtuoso can be reached, "
                    "press Save task: it writes the rows and the approved setup into the copy.")
        return dict(config=updated, validation=report.as_dict(), virtuoso=virtuoso, note=note)

    @app.post('/api/agent/reject')
    def reject(body: RejectBody):
        return _proposal_call(lambda: context.proposals.reject(body.proposal_id))

    def _audit(proposal):
        _log_line('agent_audit.jsonl', 'Agent request audit only. Never an RL run id, checkpoint or simulation budget.',
                  **{key: proposal[key] for key in ('proposal_id', 'provider', 'origin', 'kind', 'audit')})
