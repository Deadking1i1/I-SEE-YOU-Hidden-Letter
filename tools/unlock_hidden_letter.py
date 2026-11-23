from argparse import ArgumentParser
from getpass import getpass
from pathlib import Path

from hidden_letter_crypto import unlock_letter_file


def main() -> None:
    parser = ArgumentParser(description="Unlock the private I SEE YOU binary letter.")
    parser.add_argument("--payload", type=Path, default=Path("hidden_message_payload.bin"))
    parser.add_argument("--output", type=Path, default=Path("binary_letter.txt"))
    args = parser.parse_args()
    try:
        unlock_letter_file(args.payload, args.output, getpass("Secret (not echoed): "))
    except ValueError as exc:
        raise SystemExit(str(exc))
    print(f"Eight-bit binary text written to {args.output}")


if __name__ == "__main__":
    main()
