"""Prompt for the local secret and display the decrypted letter without saving it."""
from argparse import ArgumentParser
from getpass import getpass
from pathlib import Path

from hidden_letter_crypto import binary_text_to_bytes, decrypt_letter_container


def main() -> None:
    parser = ArgumentParser(description="Unlock and display the private letter.")
    parser.add_argument("--payload", type=Path, help="Encrypted payload file; defaults to the project copy.")
    args = parser.parse_args()
    payload = args.payload or (Path(__file__).resolve().parents[1] / "hidden_message_payload.bin")
    if not payload.is_file():
        raise SystemExit("Encrypted payload is missing. Keep this script beside the project files.")

    secret = getpass("Enter the PIN/secret (typing is hidden): ")
    try:
        binary_text = decrypt_letter_container(payload.read_bytes(), secret)
        message = binary_text_to_bytes(binary_text).decode("utf-8-sig", errors="replace")
    except ValueError as exc:
        raise SystemExit(f"Could not unlock the letter: {exc}") from None

    print("\nYour letter:\n")
    print(message)
    input("\nPress Enter to close this window after reading. ")


if __name__ == "__main__":
    main()
