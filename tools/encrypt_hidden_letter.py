from argparse import ArgumentParser
from getpass import getpass
from pathlib import Path

from hidden_letter_crypto import encrypt_letter_file


def main() -> None:
    parser = ArgumentParser(description="Encrypt a private letter for I SEE YOU.")
    parser.add_argument("--input", type=Path, required=True, help="private source letter; never commit it")
    parser.add_argument("--output", type=Path, default=Path("hidden_message_payload.bin"))
    args = parser.parse_args()
    secret = getpass("Secret (not echoed): ")
    confirmation = getpass("Repeat secret: ")
    if secret != confirmation:
        raise SystemExit("Secrets did not match.")
    if len(secret.encode("utf-8")) < 8:
        raise SystemExit("Use a secret of at least 8 UTF-8 bytes.")
    encrypt_letter_file(args.input, args.output, secret)
    print(f"Encrypted payload written to {args.output}")


if __name__ == "__main__":
    main()
