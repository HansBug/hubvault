import pytest

import hubvault.config as config


@pytest.mark.unittest
class TestConfigInit:
    def test_package_import_succeeds(self):
        assert config.__name__ == "hubvault.config"
        assert hasattr(config, "__path__")

