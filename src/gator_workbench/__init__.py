"""GATOR engineering workbench: configuration, run control and data-only outputs.

This package deliberately lives OUTSIDE ``analog_optimizer``. The optimizer's
``training.sac.source_digest()`` hashes every ``*.py`` file under
``analog_optimizer`` and both ``SACLearner.load`` and the M5/M6 audit scripts
require an exact match, so adding modules there would invalidate existing
checkpoints and experiment audits. The workbench only *composes* the existing
environment, learner, replay, action mapper and specification evaluator.

It produces data, configurations, models, netlists and logs. It never renders
plots, images or analysis reports and imports no plotting library.
"""

__version__ = '0.1.0'

CONFIG_SCHEMA_VERSION = 'gator-workbench-config-v1'
OUTPUT_LAYOUT_VERSION = 'gator-workbench-output-v1'
TABLE_SCHEMA_VERSION = 'gator-workbench-tables-v1'
CHECKPOINT_METADATA_VERSION = 'gator-workbench-checkpoint-v1'
EXPORTER_VERSION = 'gator-workbench-aggregates-v3'
