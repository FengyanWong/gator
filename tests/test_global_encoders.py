"""Global attention isolation, raw structural inputs and versioned architecture contracts."""
from dataclasses import replace
from types import SimpleNamespace

import pytest
import torch

from analog_optimizer.models.encoders import ModelConfig
from analog_optimizer.models.global_attention import CircuitAttention, _return_probabilities, structural_features


def test_interleaved_attention_masks_padding_and_other_circuits():
    torch.manual_seed(28)
    attention = CircuitAttention(8, 2, 'group')
    queries = torch.randn(4, 8, requires_grad=True)
    keys = torch.randn(7, 8, requires_grad=True)
    qb, kb = torch.tensor([1, 0, 1, 2]), torch.tensor([2, 0, 1, 0, 1, 2, 1])
    together = attention(queries, keys, qb, kb, 3)
    for graph in range(3):
        q, k = queries[qb == graph], keys[kb == graph]
        separate = attention(q, k, torch.zeros(len(q), dtype=torch.long), torch.zeros(len(k), dtype=torch.long), 1)
        torch.testing.assert_close(together[qb == graph], separate, atol=1e-6, rtol=1e-6)
    together[qb == 0].sum().backward()
    assert keys.grad[kb == 0].abs().sum() > 0
    assert keys.grad[kb != 0].count_nonzero() == queries.grad[qb != 0].count_nonzero() == 0
    changed = keys.detach().clone()
    changed[kb == 2] += 100
    torch.testing.assert_close(attention(queries, changed, qb, kb, 3)[qb != 2], together[qb != 2])


def test_random_walk_returns_are_correct_cached_and_permutation_equivariant():
    # Path 0--1--2, plus isolated 3. Every even walk from the centre returns;
    # either endpoint has probability 1/2. No fabricated self-loop on 3.
    edges = torch.tensor([[0, 1, 1, 2], [1, 0, 2, 1]])
    expected = torch.tensor([[.5] * 4, [1.] * 4, [.5] * 4, [0.] * 4])
    torch.testing.assert_close(_return_probabilities(4, edges, cached=False), expected)
    first = _return_probabilities(4, edges)
    first.zero_()  # A caller cannot poison the cache.
    torch.testing.assert_close(_return_probabilities(4, edges), expected)
    permutation = torch.tensor([2, 0, 3, 1])
    torch.testing.assert_close(_return_probabilities(4, permutation[edges])[permutation], expected)
    assert not torch.equal(_return_probabilities(4, edges[:, :2]), expected)
    # The actual SAC node order is devices of all graphs, then nets of all graphs.
    indices = torch.tensor([0, 2, 4, 6])
    batch = SimpleNamespace(context=torch.zeros(2, 1), node_batch=torch.tensor([0, 1, 0, 1, 0, 1, 0, 1]),
                            edge_index=torch.cat((indices[edges], (indices + 1)[edges]), dim=1))
    torch.testing.assert_close(structural_features(batch)[indices], expected)
    torch.testing.assert_close(structural_features(batch), structural_features(batch, cached=False))


@pytest.mark.parametrize('encoder', ['graph_gps', 'group_cross_attention'])
def test_architecture_contract_and_invalid_structural_options(encoder):
    config = ModelConfig(encoder_type=encoder)
    assert config.to_dict()['architecture_version'] == 1
    assert config.structural_encoding == ('rwse' if encoder == 'graph_gps' else 'none')
    assert ModelConfig(**config.to_dict()) == config
    assert replace(config, structural_encoding='rwse').to_dict() != replace(config, structural_encoding='none').to_dict()
    for args in ({'structural_encoding': 'unknown'}, {'structural_encoding': ''}, {'architecture_version': 2}, {'hidden_dim': 13}):
        with pytest.raises(ValueError):
            replace(config, **args)
    assert 'structural_encoding' not in ModelConfig().to_dict()
    with pytest.raises(ValueError):
        ModelConfig(encoder_type='graph_transformer', structural_encoding='rwse')
