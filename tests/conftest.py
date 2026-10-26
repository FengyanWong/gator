"""Shared local fixtures and safeguards that load synthetic graphs without simulator or network calls."""

import os
from pathlib import Path

import pytest

from analog_optimizer.netlist.config import ParserConfig
from analog_optimizer.netlist.spectre_parser import SpectreParser


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "synthetic"
# The workbench has no MOCK task since 2026-09-30 (record 7.128). The tests register their stand-in - the OTA5 netlist
# on the toy backend that was synthetic:gpdk045_ota5 - before anything imports gator_workbench.tasks; the run workers
# and lanes a test starts inherit the variable.
os.environ.setdefault("GATOR_WORKBENCH_SYNTHETIC_FIXTURES", str(ROOT / "tests" / "workbench" / "fixtures" / "synthetic_fixtures.json"))
# The Agent tab's buttons open Claude Code or Codex in a terminal window (agent_cli.py): never from a test. With the
# variable off a launch is a dry run that says what it would have opened and writes nothing.
os.environ["GATOR_AGENT_CLI_LAUNCH"] = "off"


@pytest.fixture(autouse=True, scope="session")
def _cheap_fsync():
    """os.fsync was about a quarter of the suite's test time (review round 5: 31,891 calls, 116 s of 499 s), and no test
    needs its bytes on the disk. In the test processes it only checks the descriptor, as fsync does (a bad one still
    raises). A test that counts or injects fsync patches os.fsync itself and wins; child processes keep the real one."""
    real = os.fsync

    def fsync(fd):
        os.fstat(fd if isinstance(fd, int) else fd.fileno())

    os.fsync = fsync
    try:
        yield
    finally:
        os.fsync = real


def pytest_runtest_setup(item):
    """requires_evidence(*paths): the test reads recorded local evidence under artifacts/, which is not in git. Where a
    path (relative to this repository, or absolute) is absent, as in any copy of the repository, the test is skipped
    with the path named, instead of failing or erroring in a fixture. Where all are present, it runs."""
    for marker in item.iter_markers("requires_evidence"):
        missing = [os.path.relpath(ROOT / path, ROOT) for path in marker.args if not (ROOT / path).exists()]
        if missing:
            pytest.skip(f"recorded evidence not in this copy of the repository (artifacts/ is not in git): {', '.join(missing)}")


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

