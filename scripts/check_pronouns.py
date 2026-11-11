#!/usr/bin/env python3
"""Flag gendered pronouns in a draft call schedule.

Usage: python -I scripts/check_pronouns.py <draft.md>

Prints each line that contains he/she/him/her/his/hers/himself/herself, with
its line number, and exits 1 if any were found (0 if none). It doesn't know
whether a pronoun is backed by a source; that's for you to decide line by line.
"""
import re
import sys

WORDS = re.compile(r"\b(he|she|him|her|his|hers|himself|herself)\b", re.IGNORECASE)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip())
        return 2
    with open(sys.argv[1], encoding="utf-8") as f:
        hits = [(n, line.rstrip("\n")) for n, line in enumerate(f, 1) if WORDS.search(line)]
    for n, line in hits:
        found = ", ".join(sorted({m.group(0).lower() for m in WORDS.finditer(line)}))
        print(f"line {n} [{found}]: {line.strip()}")
    print(f"{len(hits)} line(s) flagged" if hits else "No gendered pronouns found.")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
