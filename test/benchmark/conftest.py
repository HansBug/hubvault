import os

import pytest

pytest.importorskip("pytest_benchmark.fixture")

from tools.benchmark.common import Phase9BenchmarkConfig


@pytest.fixture(scope="session")
def phase9_config():
    scale = os.environ.get("HUBVAULT_BENCHMARK_SCALE", "standard")
    return Phase9BenchmarkConfig.from_scale(scale)

