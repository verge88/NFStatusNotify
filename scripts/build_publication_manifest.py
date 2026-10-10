#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLICATION_ROOT = ROOT / "artifacts" / "publication-freeze"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    evidence = json.loads((ROOT / "publication" / "evidence.json").read_text())
    files: list[dict[str, object]] = []

    for base in (
        ROOT / "artifacts" / "publication-freeze",
        ROOT / "artifacts" / "publication-evidence",
    ):
        if not base.exists():
            continue
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            if path.name in {"SHA256SUMS", "publication-manifest.json"}:
                continue
            files.append(
                {
                    "path": str(path.relative_to(ROOT)),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )

    manifest = {
        "schema_version": 1,
        "source_commit": os.environ.get("GITHUB_SHA"),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "reference_evidence": evidence,
        "files": files,
    }
    PUBLICATION_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = PUBLICATION_ROOT / "publication-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    checksum_path = PUBLICATION_ROOT / "SHA256SUMS"
    checksum_path.write_text(
        "".join(f"{item['sha256']}  {item['path']}\n" for item in files),
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
