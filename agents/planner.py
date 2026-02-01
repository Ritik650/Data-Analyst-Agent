"""Planner agent: (problem statement, dataset schema) -> structured analysis plan."""
from __future__ import annotations

import io

import pandas as pd

import config
from agents import llm

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "question": {"type": "string"},
                    "columns": {"type": "array", "items": {"type": "string"}},
                    "chart_type": {
                        "type": "string",
                        "enum": ["bar", "line", "scatter", "histogram", "box", "heatmap", "none"],
                    },
                    "analysis_approach": {"type": "string"},
                },
                "required": ["id", "question", "columns", "chart_type", "analysis_approach"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "questions"],
    "additionalProperties": False,
}

SYSTEM = """You are a senior data analyst planning an analysis.

Given a problem statement and a dataset schema, produce a focused analysis plan:
- 3 to {max_q} sub-questions that together answer the problem statement
- each question must be answerable with pandas/scipy on the given columns only
- prefer questions that yield concrete numbers (aggregates, correlations, statistical tests)
- pick one chart type per question that best communicates the finding ("none" if a table suffices)
- keep 'analysis_approach' to one concise sentence describing the computation"""


def describe_dataset(df: pd.DataFrame) -> str:
    """Compact schema summary given to every agent."""
    buf = io.StringIO()
    buf.write(f"rows={len(df)}, columns={len(df.columns)}\n\ndtypes:\n")
    buf.write(df.dtypes.to_string())
    buf.write("\n\nhead(5):\n")
    buf.write(df.head(5).to_string(max_cols=20))
    numeric = df.select_dtypes("number")
    if not numeric.empty:
        buf.write("\n\ndescribe (numeric):\n")
        buf.write(numeric.describe().round(3).to_string(max_cols=15))
    nulls = df.isna().sum()
    nulls = nulls[nulls > 0]
    if not nulls.empty:
        buf.write("\n\nnull counts:\n")
        buf.write(nulls.to_string())
    return buf.getvalue()[:6000]


def make_plan(problem_statement: str, schema_summary: str) -> dict:
    plan = llm.complete_json(
        system=SYSTEM.format(max_q=config.MAX_PLAN_QUESTIONS),
        user=(
            f"PROBLEM STATEMENT:\n{problem_statement}\n\n"
            f"DATASET SCHEMA:\n{schema_summary}\n\n"
            "Produce the analysis plan."
        ),
        schema=PLAN_SCHEMA,
    )
    plan["questions"] = plan["questions"][: config.MAX_PLAN_QUESTIONS]
    return plan
