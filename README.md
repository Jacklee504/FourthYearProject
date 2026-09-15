# CAPTS: Change-Aware Pipeline Test Selection

**A Format-Agnostic Framework for Selective Change-Testing of CI/CD Pipeline Definitions**

## What Is It?

A framework that selectively tests pipeline definition changes across CI
platforms. It detects what changed, traverses a typed dependency graph to
find affected stages, executes only those, and reports pass/fail with
deterministic risk scoring.

The core is a universal pipeline dependency model, applying Regression Test
Selection against it. Format-specific adapters map concrete CI formats into
this model, traversal, execution, and scoring stay format-independent.

## Motivation

Observed this problem first-hand during my placement working on CI/CD pipelines.
Testing changes required running a job that built a full test pipeline against a
changeset before functionality could be verified. This difficulty resulted in
frequent breakages and reverts.

## Why?

Pipeline definitions are versioned and reviewed like code, but unlike
application code they have no dynamic test feedback. Static validation answers
“is this valid YAML?”, not “does this change break a downstream stage that
depends on the variable just renamed?”

## How It Works

```text
git diff → format adapter parses old + new definitions
    → typed change events (variable renamed, stage removed, template modified)
    → build dependency graph from the universal model
    → select affected stages + calculate risk scores
    → execute affected stages locally
    → pass/fail verdict
```

The initial adapters target GitLab CI and GitHub Actions, demonstrating that
the same core approach works across two formats.

## Core Deliverables

1. Universal pipeline dependency model and adapter contract.
2. Graph-based selective test engine with local execution and risk scoring.
3. GitLab CI and GitHub Actions adapters.
4. Mutation-based evaluation across both formats.
