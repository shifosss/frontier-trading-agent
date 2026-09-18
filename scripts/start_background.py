"""Start a hidden worker whose standard streams do not depend on this launcher."""

import argparse
from pathlib import Path

from frontier.processes import start_background


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--working-directory", type=Path, required=True)
    parser.add_argument("--log-directory", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a worker command is required after --")
    print(start_background(command, args.working_directory, args.log_directory))


if __name__ == "__main__":
    main()
