# Publication artifact freeze

This repository separates experimental iteration from the immutable artifact
that should accompany a paper submission.

## Frozen operating point

The publication operating point is `consensus_guard` with:

- dual-source persistence: **1 sample**;
- single-source persistence: **8 samples**;
- target FPR: **0.001**.

The historical 2/12 reference remains in code for reproduction of the
pre-promotion experiments.

## Frozen Python environment

`constraints/paper-py311.txt` records the exact Python package versions
observed in successful CI run `38062366698` on main commit
`247cfe9a2ea3ef1e0173ce08d904102fb844e29e`.

The publication-freeze workflow uses Python 3.11.17 plus that constraints file,
then reruns lint, the full unit test suite and the hard-generalization benchmark.

The ordinary project metadata remains range-based so the research package can
still be tested against newer dependencies; the publication workflow is the
reproducibility path.

## Evidence registry

`publication/evidence.json` maps each intended empirical claim to the exact
GitHub Actions run and artifact that supports it. The registry includes:

- current synthetic benchmark;
- current real A→B→A failover/counterfactual result;
- current benign telemetry-degradation result;
- current real recovery/NFStatusNotify evidence;
- preregistered 1/8 candidate validation;
- development-only persistence sensitivity;
- historical replicated 2/12 study.

The freeze workflow downloads **all artifacts** from each referenced run, not
only the aggregate CSV, and places them under
`artifacts/publication-evidence/`.

## Integrity

The workflow writes:

- `environment.json` — source commit, Python/platform/tool/package versions;
- `pip-freeze.txt` — full resolved Python environment;
- a freshly recomputed publication benchmark;
- `publication-manifest.json` — evidence registry plus SHA256/size metadata;
- `SHA256SUMS` — checksums for every file in the frozen benchmark/evidence
  bundle.

The resulting GitHub artifact is retained for 90 days and is intended as the
input to a durable archive such as Zenodo or OSF.

## Claims that remain deliberately limited

The artifact supports detection of a **distributed-state post-effect** using
real Open5GS telemetry. It does not contain or deliver a forged
`NFStatusNotify` exploit payload.

The real experiments validate Open5GS v2.7.7 under the documented topology.
They do not establish a population-level FPR bound for arbitrary production
5G deployments or other 5G Core implementations.

## Manual blockers before public archival

Three items require author/owner decisions and are intentionally not invented
by automation:

1. choose and add the repository/software license;
2. add final author names/ORCIDs and `CITATION.cff`;
3. upload the consolidated freeze artifact to Zenodo/OSF and record the DOI.

After those three items, create an immutable repository release/tag pointing to
the final publication commit and cite both the commit SHA and DOI in the paper.
