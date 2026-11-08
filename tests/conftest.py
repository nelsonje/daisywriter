import datetime as dt

import pytest

from daisywriter import samples
from daisywriter.layout import LayoutSettings
from daisywriter.merge import MergeSettings
from daisywriter.pipeline import Settings

TODAY = dt.date(2026, 11, 8)


@pytest.fixture(scope="session")
def sample_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("samples")
    samples.make_samples(d)
    return d


@pytest.fixture
def settings():
    return Settings(merge=MergeSettings(today=TODAY), layout=LayoutSettings())


def pytest_addoption(parser):
    parser.addoption("--update-golden", action="store_true",
                     help="rewrite tests/golden/*.txt from the current output")
    parser.addoption("--hardware", action="store_true",
                     help="run tests that need a typewriter connected")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--hardware"):
        return
    skip = pytest.mark.skip(reason="needs a typewriter; run with --hardware")
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip)
