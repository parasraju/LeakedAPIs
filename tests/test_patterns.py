from api.patterns import (
    ALL_QUERIES,
    CODE_QUERIES,
    COMMIT_QUERIES,
    ENV_VAR_QUERIES,
    ISSUE_QUERIES,
    PATTERNS,
    PREFIX_QUERIES,
    SERVICES,
    is_placeholder,
)
from api.validators import VALIDATORS


def test_every_service_has_a_pattern():
    assert set(SERVICES) == set(PATTERNS.keys())


def test_every_scanned_service_has_a_validator():
    missing = sorted(set(PATTERNS.keys()) - set(VALIDATORS.keys()))
    assert not missing, f"scanned services without a validator: {missing}"


def test_query_lists_are_populated():
    assert ENV_VAR_QUERIES
    assert PREFIX_QUERIES
    assert ALL_QUERIES == ENV_VAR_QUERIES + PREFIX_QUERIES
    assert CODE_QUERIES
    assert ISSUE_QUERIES
    assert COMMIT_QUERIES


def test_placeholder_substrings_are_detected():
    for key in ["sk-1234567-sample", "your_api_key_here", "changeme", "test_key"]:
        assert is_placeholder(key), key


def test_x_heavy_keys_are_placeholders():
    assert is_placeholder("sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    assert is_placeholder("sk-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")


def test_low_cardinality_tails_are_placeholders():
    assert is_placeholder("sk-abcdefghijklmnopqrstuvwxyz111111111111")
    assert is_placeholder("hf_0000000000000000000000")


def test_realistic_keys_are_not_placeholders():
    assert not is_placeholder("sk-abcdef0123456789abcdef0123456789")
    assert not is_placeholder("hf_abcdefghijklmnopqrstuvwxyz0123456789abcdefgh")
    assert not is_placeholder("sk-1234567890123456789012345678901234567890")
