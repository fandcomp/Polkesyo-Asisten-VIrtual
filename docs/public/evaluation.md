# Campus Virtual Assistant — Evaluation Methodology

## Overview

The assistant is evaluated with a combination of automated dataset testing, LLM-assisted answer
scoring, and human usability testing — not a single number. This document describes the
methodology at a high level; internal scoring details are documented privately.

## Gold-QA Dataset Evaluation

A curated set of gold-standard questions and answers, covering admissions (SPMB), academic
services, administration, regulation, contact information, out-of-domain requests, and security
(prompt-injection/jailbreak) scenarios, is replayed through the real chat pipeline. Each question
is scored on:

- **Retrieval quality** — precision/recall against pinned expected sources.
- **Citation correctness** — whether the answer cites the right official document.
- **Fallback correctness** — whether the assistant correctly declines or defers when it should
  (out-of-domain, insufficient context, or a security risk), rather than guessing.
- **Groundedness** — whether the answer's claims are actually supported by the retrieved
  official context (faithfulness), whether the answer addresses the question asked (relevance),
  and whether it introduces any unsupported claim (hallucination).
- **Security robustness** — whether prompt-injection/jailbreak attempts succeed in bypassing the
  assistant's safety and grounding behavior.
- **Response latency.**

## Context-Integrity Ablation Comparison

To measure the contribution of the assistant's context-integrity mechanism, the same gold-QA
dataset is run twice: once with the mechanism active, and once with it disabled (evaluation-only
— production traffic always runs with the full mechanism active). The two runs are paired
question-by-question and compared with standard paired statistical tests (Wilcoxon signed-rank
for continuous metrics, an exact McNemar test for binary outcomes), reported alongside descriptive
effect sizes so both statistical and practical significance are visible.

## Human Usability Evaluation

Participants complete representative task scenarios (e.g. finding SPMB requirements, checking a
deadline) and complete the After-Scenario Questionnaire (ASQ) and System Usability Scale (SUS)
afterward — standard, validated usability instruments — to capture perceived ease of use and
task success independent of the automated metrics above.

## Reporting

All metrics, statistical test results, and usability scores are aggregated into exportable
reports (CSV) for research and institutional review, with per-trace detail available to
authorized administrators for diagnostic purposes.
