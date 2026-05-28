import pytest

from opensyndrome import metadata


@pytest.fixture(autouse=True)
def _clear_metadata_schema_cache():
    metadata._load_schema.cache_clear()
    yield
    metadata._load_schema.cache_clear()
