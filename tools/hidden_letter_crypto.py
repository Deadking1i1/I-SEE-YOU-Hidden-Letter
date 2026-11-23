"""Authenticated encryption for the private binary-letter payload."""

from hashlib import scrypt
import os
from pathlib import Path
import struct
import tempfile
import zlib

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


MAGIC = b"ISEEYOU1"
PLAINTEXT_MAGIC = b"BIN8"
SALT_BYTES = 16
NONCE_BYTES = 12
KEY_BYTES = 32
SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 128 * 1024 * 1024


def binary_text_from_bytes(source: bytes) -> bytes:
    """Return the source UTF-8 bytes as space-separated eight-bit groups."""
    return " ".join(f"{byte:08b}" for byte in source).encode("ascii")


def binary_text_to_bytes(binary_text: bytes) -> bytes:
    tokens = binary_text.decode("ascii").split()
    if not tokens or any(len(token) != 8 or set(token) - set("01") for token in tokens):
        raise ValueError("invalid eight-bit binary text")
    return bytes(int(token, 2) for token in tokens)


def _password_bytes(secret: str | bytes) -> bytes:
    value = secret if isinstance(secret, bytes) else secret.encode("utf-8")
    if not value:
        raise ValueError("secret must not be empty")
    return value


def _derive_key(secret: str | bytes, salt: bytes) -> bytes:
    return scrypt(
        _password_bytes(secret),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=SCRYPT_MAXMEM,
        dklen=KEY_BYTES,
    )


def encrypt_letter_bytes(source: bytes, secret: str | bytes) -> bytes:
    salt = os.urandom(SALT_BYTES)
    nonce = os.urandom(NONCE_BYTES)
    binary_text = binary_text_from_bytes(source)
    plaintext = PLAINTEXT_MAGIC + struct.pack(">I", len(binary_text)) + zlib.compress(binary_text, 9)
    ciphertext = AESGCM(_derive_key(secret, salt)).encrypt(nonce, plaintext, MAGIC)
    return MAGIC + salt + nonce + ciphertext


def decrypt_letter_container(container: bytes, secret: str | bytes) -> bytes:
    header_length = len(MAGIC) + SALT_BYTES + NONCE_BYTES
    if len(container) <= header_length or container[:len(MAGIC)] != MAGIC:
        raise ValueError("invalid encrypted letter container")
    offset = len(MAGIC)
    salt = container[offset:offset + SALT_BYTES]
    offset += SALT_BYTES
    nonce = container[offset:offset + NONCE_BYTES]
    offset += NONCE_BYTES
    try:
        plaintext = AESGCM(_derive_key(secret, salt)).decrypt(nonce, container[offset:], MAGIC)
        if len(plaintext) < len(PLAINTEXT_MAGIC) + 4 or plaintext[:len(PLAINTEXT_MAGIC)] != PLAINTEXT_MAGIC:
            raise ValueError("invalid decrypted letter payload")
        binary_length = struct.unpack(">I", plaintext[len(PLAINTEXT_MAGIC):len(PLAINTEXT_MAGIC) + 4])[0]
        binary_text = zlib.decompress(plaintext[len(PLAINTEXT_MAGIC) + 4:])
        if len(binary_text) != binary_length:
            raise ValueError("invalid decrypted letter length")
        binary_text_to_bytes(binary_text)
        return binary_text
    except Exception as exc:
        raise ValueError("secret rejected or payload was modified") from exc


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def encrypt_letter_file(input_path: Path, output_path: Path, secret: str | bytes) -> None:
    _atomic_write(output_path, encrypt_letter_bytes(input_path.read_bytes(), secret))


def unlock_letter_file(payload_path: Path, output_path: Path, secret: str | bytes) -> None:
    binary_text = decrypt_letter_container(payload_path.read_bytes(), secret)
    binary_text_to_bytes(binary_text)
    _atomic_write(output_path, binary_text)
