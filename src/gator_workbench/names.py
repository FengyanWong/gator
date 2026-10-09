"""Names and constants that several workbench modules share (refactoring package B9, docs/plan-refactoring.md). Each was
spelled out in two to six places with the same bytes; those modules now take it from here, under the names they had."""

# Patterns, as text: a module compiles its own (re keeps one compiled pattern per text), a request body hands the text
# to its field.
CADENCE_NAME = r'^[A-Za-z_][A-Za-z0-9_.\-]{0,127}$'      # a Virtuoso library, cell or instance name
PROFILE_ID = r'^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$'       # a connection profile: an identifier, never a host, port or command
TASK_NAME = r'^[a-z][a-z0-9_]{1,39}$'                    # a saved task: real:<name> or ngspice:<name>

WORKING_STATES = ('starting', 'running', 'pausing', 'stopping')    # a worker holds the run
CLEAN_EXIT_STATES = ('completed', 'paused', 'stopped')            # a run process that ends in one of these exits with 0
LOOPBACK_HOSTS = ('127.0.0.1', 'localhost', '::1')

TRASH = '.deleted'                     # a deleted task's folder moves here, inside its store; no listing looks inside
TRASH_STAMP = '%Y%m%dT%H%M%S%fZ'       # the UTC time in the name of a folder moved there
