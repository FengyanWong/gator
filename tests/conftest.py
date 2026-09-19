from pathlib import Path

import pytest

from analog_optimizer.netlist.config import ParserConfig
from analog_optimizer.netlist.spectre_parser import SpectreParser


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "synthetic"


@pytest.fixture
def config():
    return ParserConfig.from_file(ROOT / "configs" / "synthetic.json")


@pytest.fixture
def parser(config):
    return SpectreParser(config)


@pytest.fixture
def opamp():
    return SpectreParser(ParserConfig.from_file(ROOT / "configs" / "opamp.json")).parse_file(FIXTURES / "opamp.scs")


@pytest.fixture
def ldo():
    return SpectreParser(ParserConfig.from_file(ROOT / "configs" / "ldo.json")).parse_file(FIXTURES / "ldo.scs")

