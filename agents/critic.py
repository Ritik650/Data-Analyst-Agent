"""Critic agent: grounding validation.

Every numeric claim in generated prose must be traceable to the actual sandbox
stdout. Ungrounded claims trigger a regeneration; persistent offenders are
flagged in the report. This is the core differentiator of the project.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import config
from agents import llm

# Matches 1,234.56 / -3.4 / $1,200 / 45% / 0.05 — not parts of words/identifiers.
NUMBER_RE = re.compile(r"(?<![\w.])-?\$?\d[\d,]*(?:\.\d+)?%?(?![\w])")

INSIGHT_SYSTEM = """You write findings for an analytical report.

Rules:
- Use ONLY numbers that literally appear in the provided code output. You may
  round to at most 2 decimal places, but never invent, extrapolate, or compute
  new numbers.
- 2-4 sentences, plain professional prose, directly answering the question.
- If the output contains no relevant numbers, describe the qualitative pattern
  without fabricating figures."""

SUMMARY_SYSTEM = """You write the executive summary and recommendations for an
analytical report.

Rules:
- Every number you cite must literally appear in the provided verified findings
  or code outputs (rounding to <=2 decimals is allowed; inventing numbers is not).
- Executive summary: one tight paragraph answering the original problem statement.
- Recommendations: 3-5 specific, actionable items tied to the findings."""

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "executive_summary": {"type": "string"},
        "recommendations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["executive_summary", "recommendations"],
    "additionalProperties": False,
}


@dataclass
class GroundingResult:
    total_claims: int = 0
    grounded_claims: int = 0
    ungrounded: list[str] = field(default_factory=list)

    @property
    def is_grounded(self) -> bool:
        return not self.ungrounded

    @property
    def accuracy(self) -> float:
        return 1.0 if self.total_claims == 0 else self.grounded_claims / self.total_claims

    def to_dict(self) -> dict:
        return {
            "total_claims": self.total_claims,
            "grounded_claims": self.grounded_claims,
            "ungrounded": self.ungrounded,
            "accuracy": round(self.accuracy, 4),
        }


def _to_float(token: str) -> float:
    return float(token.replace("$", "").replace(",", "").replace("%", ""))


def extract_numbers(text: str) -> list[str]:
    return NUMBER_RE.findall(text)


def _decimals(token: str) -> int:
    cleaned = token.replace("$", "").replace(",", "").replace("%", "")
    return len(cleaned.split(".")[1]) if "." in cleaned else 0


def _matches(claim: float, source: float, claim_decimals: int) -> bool:
    for candidate in (claim, claim / 100.0, claim * 100.0):  # % <-> fraction forms
        if candidate == source:
            return True
        if round(source, claim_decimals) == candidate:  # rounded quote of source
            return True
        if source != 0 and abs(candidate - source) / abs(source) < 0.005:
            return True
    return False


def verify(claim_text: str, source_text: str, exempt_text: str = "") -> GroundingResult:
    """Check that every number in ``claim_text`` is traceable to ``source_text``."""
    source_numbers = [_to_float(t) for t in extract_numbers(source_text)]
    exempt_numbers = {_to_float(t) for t in extract_numbers(exempt_text)}
    result = GroundingResult()

    for token in extract_numbers(claim_text):
        value = _to_float(token)
        # ordinals / list positions / numbers quoted from the question itself
        if value in exempt_numbers or (value == int(value) and abs(value) <= 12):
            continue
        result.total_claims += 1
        if any(_matches(value, s, _decimals(token)) for s in source_numbers):
            result.grounded_claims += 1
        else:
            result.ungrounded.append(token)
    return result


def _regenerate_until_grounded(system: str, user: str, source_text: str,
                               exempt_text: str) -> tuple[str, GroundingResult]:
    text = llm.complete(system, user)
    grounding = verify(text, source_text, exempt_text)
    attempt = 0
    while not grounding.is_grounded and attempt < config.MAX_CRITIC_RETRIES:
        attempt += 1
        feedback = (
            f"{user}\n\nYour previous answer contained numbers that do NOT appear in the "
            f"code output: {', '.join(grounding.ungrounded)}.\n"
            f"PREVIOUS ANSWER:\n{text}\n\n"
            "Rewrite it using only numbers that literally appear in the code output."
        )
        text = llm.complete(system, feedback)
        grounding = verify(text, source_text, exempt_text)
    return text, grounding


def grounded_insight(question: str, stdout: str) -> tuple[str, GroundingResult]:
    """Write a finding for one plan step and verify it against the sandbox stdout."""
    user = f"QUESTION: {question}\n\nCODE OUTPUT:\n{stdout}\n\nWrite the finding."
    return _regenerate_until_grounded(INSIGHT_SYSTEM, user, stdout, exempt_text=question)


def grounded_summary(problem_statement: str, insights: list[str],
                     all_stdout: str) -> tuple[dict, GroundingResult]:
    """Executive summary + recommendations, verified against all execution output."""
    user = (
        f"PROBLEM STATEMENT:\n{problem_statement}\n\n"
        f"VERIFIED FINDINGS:\n" + "\n".join(f"- {i}" for i in insights) +
        f"\n\nFULL CODE OUTPUTS:\n{all_stdout[:15000]}\n\nWrite the summary."
    )
    source = all_stdout + "\n" + "\n".join(insights)
    summary = llm.complete_json(SUMMARY_SYSTEM, user, SUMMARY_SCHEMA)
    text_blob = summary["executive_summary"] + "\n" + "\n".join(summary["recommendations"])
    grounding = verify(text_blob, source, exempt_text=problem_statement)

    attempt = 0
    while not grounding.is_grounded and attempt < config.MAX_CRITIC_RETRIES:
        attempt += 1
        summary = llm.complete_json(
            SUMMARY_SYSTEM,
            user + (
                f"\n\nYour previous draft cited numbers not present in the findings/outputs: "
                f"{', '.join(grounding.ungrounded)}. Use only numbers that literally appear."
            ),
            SUMMARY_SCHEMA,
        )
        text_blob = summary["executive_summary"] + "\n" + "\n".join(summary["recommendations"])
        grounding = verify(text_blob, source, exempt_text=problem_statement)
    return summary, grounding
