"""Per-encoder network settings, held by the backend.

publication     values taken from analog-circuit design publications (REFERENCES / PRESETS below).
                Read-only. Every field records where it comes from and says so plainly when no
                publication reports a usable value.
                Since record 7.192 every training value is the one of the runs that learned on GATOR
                circuits on 2026-10-05 (LEARNED: starting temperature 0.01, 8 updates per evaluation and
                discount 0 compared and chosen there; learning rate 1e-3 compared later that day and chosen
                by the user, record 7.199; batch 8, warm-up 8, replay 10,000 and episode length 4 the values
                those runs were made with). Only the network sizes
                stay published. A replaced published value stays in the field's note and under
                `published`. The page calls this the starting preset.
legacy_baseline the schema defaults alone: the setting behind every GATOR result and checkpoint made
                before 2026-10-05. With it soft actor-critic is a uniform random search (record 7.183).
saved           what the operator last set for an encoder in the panel
                (<settings dir>/network_settings.json). It wins over the publication preset.

There is no "GATOR baseline" any more (record 7.191, user 2026-10-05: "Delete the gator baseline in RL
networks and keep the publication preset"). An encoder that was put on it is read as the publication
preset; the file is not rewritten (see _was_baseline).

Choosing an encoder in the UI reads ``entry(encoder)`` (saved, else publication); editing a value
writes ``saved`` for that encoder only. A configuration submitted WITHOUT a network block still gets
the schema defaults, so existing configurations, tests and checkpoints keep their meaning (static
validation warns that those values do not learn).

Presets are ordinary ``ModelConfig`` / ``SACConfig`` / collector values of the existing algorithm;
nothing here touches ``src/analog_optimizer/``. A published value is a starting point with a
citation, not evidence that it is better on this project's circuits: none was evaluated here.
"""
from __future__ import annotations

import threading

from pydantic import ValidationError

from .paths import local_settings_dir
from .schema import ENCODER_TYPES, AdvancedRL, NetworkConfig
from .storage.atomic import read_json, write_json
from .storage.dataset import utcnow

SETTINGS_FILE = 'network_settings.json'
SETTINGS_SCHEMA = 'gator-workbench-network-settings-v1'
DEFAULT_ENCODER = 'graph_transformer'
ATTENTION_ENCODERS = ('graph_transformer', 'gatv2')         # the only blocks that read `heads`
NETWORK_FIELDS = ('hidden_dim', 'heads', 'layers')
ADVANCED_FIELDS = ('learning_rate', 'gamma', 'tau', 'initial_alpha', 'target_entropy_per_action', 'max_grad_norm',
                   'batch_size', 'warmup_transitions', 'update_every', 'updates_per_transition', 'replay_capacity',
                   'episode_length')
# paper: stated in the publication. official_code: read from the authors' released code.
# adapted: derived from a published value, changed to fit this architecture (the note says how).
# gator_default: no publication reports a usable value; the GATOR default is kept.
# gator_tested: compared on GATOR circuits and chosen (COMPARED: TESTED, record 7.183; learning rate, record 7.199).
# gator_measured_with: the value the measurements of record 7.183 were made with, not a compared optimum (LEARNED).
# not_used: the encoder ignores the field; the value only keeps checkpoints comparable.
BASES = ('paper', 'official_code', 'adapted', 'gator_default', 'gator_tested', 'gator_measured_with', 'not_used')
# same: the cited work uses this kind of network. closest: no publication uses this network for the
# purpose, so the closest published network is cited instead (the note says which and why).
MATCHES = ('same', 'closest')
_LOCK = threading.Lock()

# The soft actor-critic values compared and chosen on 2026-10-05 (record 7.183; numbers, scripts and run data in
# artifacts/local/reviews/defaults-study-2026-10-05/README.md): 175 runs on two ngspice circuits and five Spectre runs on
# real:mscr_ota7t. With the schema defaults (0.2, 1, 0.99) the designs are a uniform random search under every reward
# setting; with these, the share of passing designs in the last third of 1,500 evaluations went from 1 % to 98 %.
TESTED = dict(initial_alpha=0.01, updates_per_transition=8, gamma=0.0)
# Every training value of the runs that learned there: TESTED and the values those measurements were made with (the
# schema defaults). Each preset takes all of them in place of its published ones (record 7.192, the user: "merge the
# publication preset and overwrite those settings with the previous learned settings", then "All training numbers":
# network shape from the papers, every training number from the runs that learned). Target smoothing, target entropy,
# gradient limit and update interval are left out: every preset already has the runs' values (0.005, 1, 10, 1).
# Learning rate 1e-3 instead of those runs' 3e-4 (record 7.199, the user: "use learning rate 1e-3 in the starting preset"):
# compared with 8 updates and discount 0 the same day (calibration study), it learned earlier.
LEARNED = dict(TESTED, batch_size=8, learning_rate=1e-3, warmup_transitions=8, replay_capacity=10000, episode_length=4)
COMPARED = (*TESTED, 'learning_rate')          # the LEARNED values that were compared on GATOR circuits and chosen
TESTED_SINCE = '2026-10-05T05:00:00+00:00'
# The GATOR baseline was deleted on 2026-10-05 (record 7.191); a backend not yet restarted could still store it that day.
BASELINE_DELETED = '2026-10-06T00:00:00+00:00'
_MADE_WITH = 'The value the measurements of 2026-10-05 were made with (record 7.183).'
LEARNED_NOTES = dict(
    initial_alpha='Measured on GATOR circuits (record 7.183): at 0.2 the exploration term is several times any reward '
                  'difference and never comes down within a run. 0.05 learns as early but ends lower (88 % passing against '
                  '97 %); 0.002 learns twice as late.',
    updates_per_transition='Measured on GATOR circuits (record 7.183): with 1 nothing learns, whatever the temperature, batch '
                           'or learning rate. 4 learns at about evaluation 1,000, 8 at about 470, 16 at about 330. One '
                           'update takes 0.1 to 0.15 s.',
    gamma='Measured on GATOR circuits (record 7.183): an action is a whole design and its reward is that design\'s own '
          'measurement, so later steps add only noise. With 8 updates: learned at evaluation 269 instead of 466.',
    batch_size=_MADE_WITH + ' Batch 32 was tried: with 4 updates per evaluation it learned a little earlier than 8 (at '
                            'evaluation 785 and 887 against 956 to 1,101) at four times the cost per update. Batch 64 with 8 '
                            'updates took 4 s per design and was stopped.',
    learning_rate='Compared on GATOR circuits and chosen (record 7.199): with 8 updates per evaluation and discount 0 '
                  '(ngspice ota5, Graph Transformer 32 / 4 / 2, 1,000 evaluations, three seeds; '
                  'artifacts/local/reviews/calibration-study-2026-10-05) 1e-3 learned at evaluation 139 to 179 against 251 '
                  'to 294 with 3e-4, and 98 % of the last third passed against 93 %; its passing designs drew about 5 % more '
                  'power. The user chose 1e-3 on 2026-10-05.',
    warmup_transitions=_MADE_WITH + ' Warm-up 64 with 8 updates brought no gain (learned at evaluation 412 to 595 against '
                                    '439 to 500).',
    replay_capacity=_MADE_WITH + ' Every design of a run stays in memory (the runs had at most 1,500 evaluations). Not '
                                 'varied.',
    episode_length=_MADE_WITH + ' Not varied. With discount 0 the end of an episode changes no learning target.')
TESTED_NOTE = ('GATOR\'s own measurement (record 7.183, 2026-10-05): with a starting temperature of 0.2 and one update per '
               'evaluation - the values behind every earlier GATOR run, and what a published one-update setting amounts to at '
               'these budgets - soft actor-critic stayed a uniform random search for 1,500 evaluations on two ngspice '
               'circuits and for 922 designs on Spectre (real:mscr_ota7t, none passing). With temperature 0.01 and 8 updates '
               'per evaluation it learned after 250 to 600 evaluations (36 of 760 Spectre designs passing); discount 0 '
               'halved that on ngspice. Every preset takes these three, learning rate 1e-3 (compared later that day, record '
               '7.199: learning started about 100 evaluations earlier than with those runs\' 3e-4) and the other training '
               'values those runs were made with - batch 8, warm-up 8, replay 10,000, episode length 4 - in place of the '
               'published ones (record 7.192). The runs used a 32 / 4 / 2 network; the presets keep the published network '
               'sizes, which learned as early with these values on ngspice; on Spectre the Graph Transformer preset passed '
               '469 of 760 designs against 36 (record 7.199).')

SCALE_NOTE = ('Scale: the cited studies spent between 300 steps (CAN) and about 50,000 simulations per run, and the only '
              'published soft actor-critic settings (PPAAS) were used with 8,000 to 24,000 steps. GATOR real runs so '
              'far used tens to hundreds of evaluations each, so their training numbers do not transfer: every preset '
              'takes the training values of the runs that learned on GATOR circuits instead (records 7.192, 7.199), with '
              'which learning started after about 150 to 600 evaluations. The network sizes are still the published ones; '
              'with these training values each of them learned as early as 32 / 4 / 2 on ngspice, and on Spectre '
              '(real:mscr_ota7t) the Graph Transformer preset passed 469 of 760 designs, the first at design 202, against 36 '
              'and 591 for the setting measured before (record 7.199). For an equal-size encoder comparison give every '
              'encoder the same sizes. A saved model always loads with the network it was trained with.')


def _field(value, basis, source=None, note='', match='same'):
    return dict(value=value, basis=basis, source=source, note=note, match=match)


def _learned(name, why=''):
    """A training value of the runs that learned on GATOR circuits (LEARNED), saying whether it was compared and chosen."""
    return _field(LEARNED[name], 'gator_tested' if name in COMPARED else 'gator_measured_with',
                  note=(why + ' ' if why else '') + LEARNED_NOTES[name])


def _defaults(note='No publication for this encoder reports a usable value; GATOR default kept.'):
    network, advanced = NetworkConfig().model_dump(), AdvancedRL().model_dump()
    return {name: _learned(name, 'No publication for this encoder reports a usable value.') if name in LEARNED
            else _field({**network, **advanced}[name], 'gator_default', note=note)
            for name in NETWORK_FIELDS + ADVANCED_FIELDS}


# --------------------------------------------------------------------------- publications
# Every value below was read in the primary source (paper text or the authors' code) on 2026-09-20;
# docs/network-presets.md holds the verbatim quotes. `budget` is what the study spent per run: it is
# the reason a published batch size or warm-up does not transfer to a run of a few dozen evaluations.
def _reference(short, authors, title, venue, year, url, algorithm, budget, code=None):
    return dict(short=short, authors=authors, title=title, venue=venue, year=year, url=url, algorithm=algorithm,
                budget=budget, code=code)


REFERENCES: dict = {
    'li2023rgcn': _reference(
        'Li & Chan Carusone, ICCAD 2023', 'Z. Li, A. Chan Carusone',
        'Design and Optimization of Low-Dropout Voltage Regulator Using Relational Graph Neural Network and '
        'Reinforcement Learning in Open-Source SKY130 Process',
        'ICCAD', 2023, 'https://doi.org/10.1109/ICCAD57390.2023.10323720', 'DDPG',
        '10,000 (LDO1) and 20,000 (LDO2) Ngspice simulations per run.',
        code='https://github.com/ChrisZonghaoLi/sky130_ldo_rl'),
    'cao2022gat': _reference(
        'Cao et al., DAC 2022', 'W. Cao, M. Benosman, X. Zhang, R. Ma',
        'Domain Knowledge-Infused Deep Learning for Automated Analog/Radio-Frequency Circuit Parameter Optimization',
        'DAC', 2022, 'https://arxiv.org/abs/2204.12948', 'PPO',
        'Up to 35,000 episodes of 50 steps (op-amp). The paper states no GAT sizes; they are in the authors\' '
        'repository, whose README names no paper.',
        code='https://github.com/xz-group/AutoSizing'),
    'gursoy2026lighthouse': _reference(
        'Gursoy et al., arXiv 2026 (Lighthouse RL)',
        'M. E. Gursoy, S. Uhlich, R. Matsuo, Y. Gencer, A. Venkitaraman, C.-Y. Hsieh, A. Bonetti, E. Ohbuchi, '
        'L. Servadei',
        'Lighthouse RL: Sample-Efficient Circuit Optimization via Strategic Reset Points',
        'arXiv:2607.14008', 2026, 'https://arxiv.org/abs/2607.14008', 'SAC',
        '6,000 (two-stage op-amp) and 30,000 (multistage amplifier) Ngspice simulations. Width, heads, learning '
        'rate, batch and replay size are not reported.'),
    'li2021can': _reference(
        'Li et al., MLCAD 2021 (CAN)',
        'Y. Li, Y. Lin, M. Madhusudan, A. Sharma, S. Sapatnekar, R. Harjani, J. Hu',
        'A Circuit Attention Network-Based Actor-Critic Learning Approach to Robust Analog Transistor Sizing',
        'MLCAD', 2021, 'https://doi.org/10.1109/MLCAD52597.2021.9531156', 'DDPG',
        '300 training steps, each reward averaged over 100 Monte-Carlo simulations.'),
    'fan2024gtn': _reference(
        'Fan et al., DAC 2024 (GTN)', 'S. Fan, H. Lu, S. Zhang, N. Cao, X. Zhang, J. Li',
        'Graph-Transformer-based Surrogate Model for Accelerated Converter Circuit Topology Design',
        'DAC', 2024, 'https://doi.org/10.1145/3649329.3656258', 'supervised surrogate inside a tree search',
        'Not an RL agent: trained on 0.33% to 1.98% of 959,000 simulated power converters for 700 epochs. Learning '
        'rate, optimizer and batch size are not reported.'),
    'ren2020paragraph': _reference(
        'Ren et al., DAC 2020 (ParaGraph)', 'H. Ren, G. F. Kokai, W. J. Turner, T.-S. Ku',
        'ParaGraph: Layout Parasitics and Device Parameter Prediction using Graph Neural Networks',
        'DAC', 2020, 'https://doi.org/10.1109/DAC18072.2020.9218515', 'supervised regression',
        'Not an optimization loop: 18 training and 4 test circuits, 300 epochs.'),
}

_NOT_USED = _field(NetworkConfig().heads, 'not_used', note='This encoder has no attention heads. The number is still '
                   'written into every checkpoint, so it stays at the GATOR value.')
_NO_ENTROPY = 'The cited study uses {algorithm}, which has no entropy temperature; GATOR default kept.'


MEASURED_SUMMARY = (' The training values are those of the runs that learned on GATOR circuits (records 7.183, 7.199) and replace '
                    'the published ones (record 7.192); each field\'s note keeps the published value. The network sizes '
                    'above stay as published; those runs used 32 / 4 / 2, and this size learned as early with the same '
                    'values on ngspice (record 7.199).')


def _preset(summary, **fields):
    """Every field starts as the GATOR default and says so; a preset overrides what a publication supports. Then every
    training value of the runs that learned on GATOR circuits (LEARNED) replaces the published one (record 7.192): the
    published field is kept under `published` and named in the note. A published value equal to the learned one stays as
    it is, and says so."""
    merged = _defaults()
    merged.update(fields)
    for name in LEARNED:
        published = merged[name]
        if published['basis'] in ('gator_tested', 'gator_measured_with'):
            continue
        if published['value'] == LEARNED[name]:
            merged[name] = dict(published, note=published['note'] + ' Also the GATOR value. ' + LEARNED_NOTES[name])
            continue
        cited = REFERENCES[published['source']]['short'] if published['source'] else 'GATOR default'
        merged[name] = dict(_learned(name, f"Published: {published['value']:g} ({cited}); replaced by the GATOR value."),
                            published=published)
    return dict(summary=summary + MEASURED_SUMMARY, fields=merged)


def _li2023_training(note='', match='same'):
    """The one fully documented off-policy sizing setup with a graph network (DDPG, 50-step episodes)."""
    key = 'li2023rgcn'
    return dict(
        learning_rate=_field(3e-4, 'official_code', key, 'Adam 3e-4 for actor and critic (ddpg.py); the paper '
                             'states no learning rate.' + note, match),
        gamma=_field(0.99, 'paper', key, 'Algorithm 2: gamma = 0.99.' + note, match),
        tau=_field(0.005, 'paper', key, 'Algorithm 2: target smoothing rho = 0.005.' + note, match),
        batch_size=_field(128, 'paper', key, '"the batch size B is 128".' + note, match),
        warmup_transitions=_field(1000, 'paper', key, '"1000 and 4000 initial random exploration steps for LDO1 '
                                  'and LDO2": the smaller circuit\'s value.' + note, match),
        update_every=_field(1, 'official_code', key, 'One update per environment step after warm-up.' + note, match),
        updates_per_transition=_field(1, 'official_code', key, 'One gradient step per update.' + note, match),
        replay_capacity=_field(100000, 'paper', key, '"the size of our memory buffer M is 100000".' + note, match),
        episode_length=_field(50, 'paper', key, '"The episode length w is 50".' + note, match),
        initial_alpha=_learned('initial_alpha', 'The cited study uses DDPG, which has no entropy temperature.'),
        target_entropy_per_action=_field(AdvancedRL().target_entropy_per_action, 'gator_default',
                                         note=_NO_ENTROPY.format(algorithm='DDPG')),
        max_grad_norm=_field(AdvancedRL().max_grad_norm, 'gator_default',
                             note='The cited code clips no gradients; GATOR requires a positive limit, default kept.'))


def _attention_training(note='', match='same'):
    """What attention-network sizing agents report: CAN (DDPG, 300-step budget) and Lighthouse RL (SAC)."""
    return dict(
        learning_rate=_field(1e-3, 'adapted', 'li2021can', '"learning rates for the actor and critic are set as '
                             '0.001 and 0.002". GATOR has one learning rate; the actor\'s is used. The Cao et al. '
                             'PPO code uses 5e-4.' + note, match),
        gamma=_field(0.9, 'paper', 'li2021can', '"The reward discount is 0.9." The Cao et al. PPO code uses 0.95.'
                     + note, match),
        batch_size=_field(32, 'paper', 'li2021can', '"The training batch size 32."' + note, match),
        replay_capacity=_field(50, 'paper', 'li2021can', '"The replay buffer size is 50". Unusually small: the '
                               'study ran 300 steps in total. Raise it for longer runs.' + note, match),
        episode_length=_field(30, 'paper', 'gursoy2026lighthouse', '"An episode consists of 30 time steps". Cao et '
                              'al. use 50 (op-amp) and 30 (power amplifier).' + note, match))


PRESETS: dict = {
    'graph_transformer': _preset(
        'Size from the only published analog graph transformer whose attention is restricted to graph neighbours, '
        'like the GATOR block (GTN, a supervised surrogate for power converters). No publication uses a graph '
        'transformer as the RL sizing agent, so the published training numbers in the notes are those reported for '
        'attention-network sizing agents (also borrowed by the gatv2 preset); the GATOR graph_transformer and gatv2 '
        'blocks differ in the attention function.',
        layers=_field(4, 'paper', 'fan2024gtn', '"we construct GTN by comprising a total of 4 layers with ReLU '
                      'activation".'),
        hidden_dim=_field(48, 'paper', 'fan2024gtn', '"encode vertices into embeddings with dimension of 48".'),
        heads=_field(4, 'paper', 'fan2024gtn', '"we configure the number of heads as 4 and D_k as 6".'),
        **_attention_training(' Borrowed from a GAT-style agent: no graph-transformer sizing agent is published.',
                              'closest')),
    'rgcn': _preset(
        'Sizes and the published training numbers (in the notes) from the one published line of work that puts an '
        'R-GCN inside a transistor-sizing RL loop '
        '(DDPG on two LDOs). Its two edge types are hand-annotated signal/bias paths; GATOR types edges by '
        'terminal role and direction instead.',
        layers=_field(4, 'official_code', 'li2023rgcn', 'Four RGCNConv layers in models.py (the paper shows them '
                      'only in a figure).'),
        hidden_dim=_field(32, 'adapted', 'li2023rgcn', 'RGCNConv widths 32-32-16-16 with num_bases = 32; GATOR '
                          'blocks have one width, the first is used.'),
        heads=_NOT_USED, **_li2023_training()),
    'gatv2': _preset(
        'GATv2 replaces GATv1 with dynamic attention. These starting values are borrowed from the previous '
        'GAT preset; they are not a verified GATv2 circuit-sizing recipe. Depth and the published episode length '
        'come from a SAC agent with residual, layer-normalized GAT layers; heads and width from GAT sizing code using '
        'PPO; the published replay-side numbers from an off-policy attention-network sizing study with a 300-step '
        'budget.',
        layers=_field(4, 'paper', 'gursoy2026lighthouse', '"four Graph Attention Network (GAT) layers with '
                      'residual connections and layer normalization". Borrowed depth for GATv2, not a GATv2 '
                      'result. CAN also uses four attention layers; the Cao et al. code uses three.', 'closest'),
        heads=_field(3, 'official_code', 'cao2022gat', 'num_heads = 3 in main_train_gan_fc.py. The paper states '
                     'no head count; borrowed from GAT for GATv2.', 'closest'),
        hidden_dim=_field(192, 'official_code', 'cao2022gat', 'n_latent_var = 64 * num_heads: 64 per head, '
                          'concatenated. Borrowed width for GATv2; separate source/target projections increase '
                          'parameter count at the same width.', 'closest'),
        **_attention_training(' Borrowed attention-network settings, not verified GATv2 sizing settings.', 'closest')),
}


# --------------------------------------------------------------------------- machinery
class InvalidNetworkSettings(ValueError):
    """A value set that the run schema (or the attention divisibility rule) would reject."""


def legacy_baseline() -> dict:
    """The schema defaults: the one setting behind all GATOR evidence and checkpoints made before 2026-10-05, and what a
    configuration without a network block still gets."""
    network, advanced = NetworkConfig().model_dump(), AdvancedRL().model_dump()
    return dict(network={f: network[f] for f in NETWORK_FIELDS}, advanced={f: advanced[f] for f in ADVANCED_FIELDS})


def _was_baseline(values, saved_utc) -> bool:
    """Saved values that were the deleted GATOR baseline (record 7.191): the schema's sizes with TESTED, or - saved before
    TESTED_SINCE, when that was the baseline - the schema defaults alone. The user's own graph_transformer entry of
    2026-10-03 is one of these. The same numbers saved after the deletion were typed by the operator and are kept."""
    legacy, saved_utc = legacy_baseline(), str(saved_utc or '')
    tested = dict(network=legacy['network'], advanced={**legacy['advanced'], **TESTED})
    return saved_utc < BASELINE_DELETED and (values == tested or (values == legacy and saved_utc < TESTED_SINCE))


def check(encoder, network, advanced) -> dict:
    """Validate ONE complete value set with the same models that validate a run configuration."""
    if encoder not in ENCODER_TYPES:
        raise KeyError(encoder)
    if not isinstance(network, dict) or not isinstance(advanced, dict):
        raise InvalidNetworkSettings('network and advanced must be objects')
    unknown = [k for k in network if k not in NETWORK_FIELDS] + [k for k in advanced if k not in ADVANCED_FIELDS]
    if unknown:
        raise InvalidNetworkSettings(f'not a per-encoder setting: {sorted(unknown)}')
    try:
        net, adv = NetworkConfig(encoder_type=encoder, **network), AdvancedRL(**advanced)
    except ValidationError as exc:
        raise InvalidNetworkSettings('; '.join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors())) from None
    if encoder in ATTENTION_ENCODERS and net.hidden_dim % net.heads:
        raise InvalidNetworkSettings(f'hidden_dim ({net.hidden_dim}) must be divisible by heads ({net.heads}) '
                                     f'for {encoder}')
    return dict(network={f: getattr(net, f) for f in NETWORK_FIELDS},
                advanced={f: getattr(adv, f) for f in ADVANCED_FIELDS})


def publication(encoder) -> dict:
    fields = PRESETS[encoder]['fields']
    return check(encoder, {f: fields[f]['value'] for f in NETWORK_FIELDS},
                 {f: fields[f]['value'] for f in ADVANCED_FIELDS})


def _path():
    return local_settings_dir() / SETTINGS_FILE


def _saved() -> tuple[dict, str | None]:
    """(saved values per encoder, problem). An unreadable file is reported, never guessed at or overwritten."""
    try:
        data = read_json(_path(), default=None)
    except ValueError as exc:
        return {}, f'{SETTINGS_FILE} is not valid JSON ({exc}); repair or delete it. Publication presets are shown.'
    encoders = data.get('encoders') if isinstance(data, dict) else None
    return (encoders if isinstance(encoders, dict) else {}), None


def _store(encoder, values):
    """values=None forgets the encoder's saved values (= back to the publication preset)."""
    encoders, problem = _saved()
    if problem:
        raise InvalidNetworkSettings(problem)
    if values is None:
        encoders.pop(encoder, None)
    else:
        encoders[encoder] = dict(values, saved_utc=utcnow().isoformat())
    write_json(_path(), dict(schema=SETTINGS_SCHEMA, encoders=encoders))


def entry(encoder) -> dict:
    """Everything the panel shows for one encoder. `network`/`advanced` are what choosing it loads."""
    if encoder not in ENCODER_TYPES:
        raise KeyError(encoder)
    preset = publication(encoder)
    encoders, problem = _saved()
    saved, values = encoders.get(encoder), preset
    if saved is not None:
        try:
            values = check(encoder, {**preset['network'], **saved['network']},
                           {**preset['advanced'], **saved['advanced']})
            # Put on the GATOR baseline, which is deleted: the publication preset is the setting kept (record 7.191).
            if _was_baseline(values, saved.get('saved_utc')):
                values, saved = preset, None
        except (InvalidNetworkSettings, KeyError, TypeError) as exc:       # hand-edited or outdated file
            problem = f'The saved {encoder} values were ignored: {exc}'
    origin = 'publication' if values == preset else 'custom'
    return dict(encoder_type=encoder, uses_heads=encoder in ATTENTION_ENCODERS, origin=origin,
                network=values['network'], advanced=values['advanced'], publication=preset,
                provenance=PRESETS[encoder]['fields'], summary=PRESETS[encoder]['summary'],
                saved_utc=saved.get('saved_utc') if isinstance(saved, dict) and problem is None else None,
                problem=problem)


def save(encoder, network=None, advanced=None) -> dict:
    """Merge the given fields over the encoder's current values, validate the WHOLE set, persist it."""
    with _LOCK:
        current = entry(encoder)
        values = check(encoder, {**current['network'], **(network or {})}, {**current['advanced'], **(advanced or {})})
        _store(encoder, None if values == publication(encoder) else values)
        return entry(encoder)


def describe() -> dict:
    return dict(encoders=list(ENCODER_TYPES), default_encoder=DEFAULT_ENCODER,
                attention_encoders=list(ATTENTION_ENCODERS), network_fields=list(NETWORK_FIELDS),
                advanced_fields=list(ADVANCED_FIELDS), legacy_baseline=legacy_baseline(),
                tested=dict(values=dict(TESTED), since=TESTED_SINCE, note=TESTED_NOTE), learned=dict(LEARNED),
                references=REFERENCES,
                scale_note=SCALE_NOTE, settings={name: entry(name) for name in ENCODER_TYPES})
