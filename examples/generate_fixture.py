"""Generate a fictional two-market source directory; see examples/README.md."""

import argparse
from pathlib import Path

from frontier.fixtures import generate_fixture

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--seed", type=int, default=1729)
    arguments = parser.parse_args()
    generate_fixture(arguments.destination, arguments.seed)
