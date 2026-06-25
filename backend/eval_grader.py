"""Eval-the-grader: check the LLM judge is calibrated against a small labeled set.

The grader (services/ai.grade) scores interview answers 0-10. Here we feed it
answers we have pre-labeled as strong / partial / wrong and assert the score
lands in the expected band. This catches a judge that drifts (rubber-stamps
everything high, or is uniformly harsh).

Run:  PYTHONPATH=. .venv/bin/python eval_grader.py
Needs an AI key (GROQ_API_KEY or ANTHROPIC_API_KEY); skips gracefully otherwise.
"""
from __future__ import annotations

import asyncio
import sys

from app.services import ai

# (question, answer, expected_low, expected_high, label). Bands are wide on
# purpose: we test direction and calibration, not exact points.
CASES = [
    (
        "Explain BM25 and where it fits in hybrid retrieval.",
        "BM25 is a sparse lexical ranking function built on TF-IDF with term-frequency "
        "saturation and document-length normalization. In hybrid search you fuse it with "
        "dense vector scores, for example via reciprocal rank fusion, so you keep exact-term "
        "matching while adding semantic recall.",
        7, 10, "strong",
    ),
    (
        "Explain BM25.",
        "I think it is some kind of database index used in SQL queries.",
        0, 4, "wrong",
    ),
    (
        "What is reciprocal rank fusion (RRF)?",
        "It combines rankings. You add up the positions somehow to get a final order.",
        3, 7, "partial",
    ),
    (
        "How do you evaluate a RAG system's retrieval quality?",
        "Build an offline eval set with labeled relevant chunks and measure recall@k and MRR, "
        "then add an LLM-as-judge for answer faithfulness and groundedness against the retrieved "
        "context. Track both retrieval and end-to-end answer metrics.",
        7, 10, "strong",
    ),
]


async def main() -> int:
    if ai.provider() == "none":
        print("No AI key configured; skipping grader eval (set GROQ_API_KEY or ANTHROPIC_API_KEY).")
        return 0

    print(f"Evaluating the grader via provider={ai.provider()}\n")
    passed = 0
    out_of_band = []
    for q, a, lo, hi, label in CASES:
        res = await ai.grade(q, a)
        s = res.get("score")
        ok = s is not None and lo <= s <= hi
        passed += int(ok)
        if s is not None and not ok:
            out_of_band.append(min(abs(s - lo), abs(s - hi)))
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:8s} score={s} (expected {lo}-{hi})")

    n = len(CASES)
    mae = sum(out_of_band) / len(out_of_band) if out_of_band else 0.0
    print(f"\n{passed}/{n} within expected band  |  mean out-of-band error: {mae:.2f}")
    # Allow one miss for LLM variance; more than one means the judge is miscalibrated.
    return 0 if passed >= n - 1 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
