#!/usr/bin/env python3
"""Audit real acquired evidence times without modifying detector observations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from nfnotify_lab.real_source_audit import run_audit, write_audit


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--observations", type=Path, required=True)
    p.add_argument("--polls", type=Path, required=True)
    p.add_argument("--routes", type=Path, required=True)
    p.add_argument("--notifications", type=Path, required=True)
    p.add_argument("--ausf-log", type=Path, required=True)
    p.add_argument("--meta", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    observations, verdict = run_audit(
        args.observations, args.polls, args.routes,
        args.notifications, args.ausf_log, args.meta,
    )
    write_audit(args.out, observations, verdict)
    print(json.dumps(verdict, indent=2))


if __name__ == "__main__":
    main()
