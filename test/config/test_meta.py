import pytest

from hubvault.config.meta import __AUTHOR__, __AUTHOR_EMAIL__, __DESCRIPTION__, __TITLE__, __VERSION__


@pytest.mark.unittest
class TestConfigMeta:
    def test_title(self):
        assert __TITLE__ == 'hubvault'

    def test_other_metadata(self):
        assert __VERSION__
        assert 'local ML artifacts' in __DESCRIPTION__
        assert 'HansBug' in __AUTHOR__
        assert '@' in __AUTHOR_EMAIL__
