"""Assert an expected action rejection without emitting workflow annotations."""
import argparse
import subprocess


def assert_failure(expected: str, command: list[str]) -> None:
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    for line in result.stdout.splitlines():
        print(f"Expected rejection output: {line}")
    if result.returncode != 1:
        raise SystemExit(f"Expected action exit code 1; got {result.returncode}")
    if expected not in result.stdout:
        raise SystemExit(f"Expected rejection reason was not found: {expected}")
    print(f"Verified expected rejection: {expected}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("expected")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.command:
        parser.error("an action command is required")
    assert_failure(args.expected, args.command)


if __name__ == "__main__":
    main()
