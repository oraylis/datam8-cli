import pytest
from pytest_cases import parametrize_with_cases
from test_020_helper_cases import (
    AlgorithmCases,
    HashCases,
    UuidCases,
)

from datam8.utils import hasher as hashutils


@parametrize_with_cases("algorithm", cases=AlgorithmCases, glob="*_valid")
@parametrize_with_cases("input", cases=HashCases, glob="*_valid")
def test_hasher_hash(input, algorithm):
    input, checksum = input
    hasher = hashutils.Hasher(algorithm)
    hash = hasher.hash(input)

    assert hash.hexdigest() == checksum


@parametrize_with_cases("algorithm", cases=AlgorithmCases, glob="*_valid")
@parametrize_with_cases("input", cases=UuidCases, glob="*_valid")
def test_hasher_create_uuid(input, algorithm):
    input, checksum = input
    hasher = hashutils.Hasher(algorithm)
    uuid = hasher.create_uuid(input)

    assert str(uuid) == checksum


@parametrize_with_cases("algorithm", cases=AlgorithmCases, glob="*_invalid")
def test_hasher(algorithm):
    with pytest.raises(hashutils.UnknownAlgorithmError):
        hashutils.Hasher(algorithm)
