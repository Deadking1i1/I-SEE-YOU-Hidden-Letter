import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from hidden_letter_crypto import (  # noqa: E402
    binary_text_from_bytes,
    binary_text_to_bytes,
    decrypt_letter_container,
    encrypt_letter_bytes,
)


def test_authenticated_binary_letter_round_trip_and_tamper_rejection():
    source = "Private test letter — UTF-8 ✓".encode("utf-8")
    secret = "unit-test-only secret"
    container = encrypt_letter_bytes(source, secret)
    assert source not in container
    assert binary_text_from_bytes(source) not in container
    assert binary_text_to_bytes(decrypt_letter_container(container, secret)) == source
    with pytest.raises(ValueError):
        decrypt_letter_container(container, "wrong secret")
    tampered = bytearray(container)
    tampered[-1] ^= 1
    with pytest.raises(ValueError):
        decrypt_letter_container(bytes(tampered), secret)
