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
