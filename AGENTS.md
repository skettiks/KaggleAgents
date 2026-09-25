# Project Instructions

## Product goal

Build a reproducible Kaggle experiment system that optimizes validation quality under explicit time, token, and compute budgets.

This repository is a reusable foundation. Competition-specific rules, metrics, splits, features, models, and experiments belong in separate competition projects using a pinned foundation version.

## Current phase

The project is in Phase 0: audit and vertical-slice definition. Prefer one working tabular path over generalized infrastructure.

## Engineering rules

- Keep full datasets, raw web pages, model files, and full logs out of LLM context and Git.
- Use versioned files and the run registry as the source of truth.
- Every experiment must have a hypothesis, budget, split, seed, result, and decision.
- Never submit to Kaggle automatically. Produce and validate an artifact, then require human approval.
- Never expose Kaggle or cloud credentials to web research or untrusted pull requests.
- Prefer deterministic narrow tools over unrestricted shell workflows.
- Do not add an agent role until it has a distinct responsibility and measurable output.
- Keep the core independent of competition slugs, column names, and model provider IDs.
- Validate reusability on a second competition before generalizing an interface.
- Clearly distinguish proposed interfaces from implemented commands in documentation.

## Implementation order

1. Telemetry and baseline measurements.
2. Deterministic data and experiment tools.
3. Persistent state and recovery.
4. Agent roles and permission boundaries.
5. Promotion gates and evaluation.

Read `docs/decisions.md` before making architecture choices and update it when a decision changes. Follow `docs/development-plan.md` for milestones and `docs/architecture.md` for ownership boundaries.
