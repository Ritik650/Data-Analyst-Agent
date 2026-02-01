"""Report rendering test — HTML path only (PDF depends on system libs)."""
from report.generate_report import render_html

SAMPLE_PAYLOAD = {
    "title": "Test Report",
    "problem_statement": "Which region drives revenue?",
    "generated_at": "2026-07-04 12:00 UTC",
    "dataset": {"filename": "sales.csv", "rows": 100, "cols": 3,
                "columns": [{"name": "region", "dtype": "object"},
                            {"name": "revenue", "dtype": "float64"}]},
    "executive_summary": "North leads with total revenue of 9000.00.",
    "recommendations": ["Invest in the North region."],
    "summary_grounding": {"total_claims": 1, "grounded_claims": 1,
                          "ungrounded": [], "accuracy": 1.0},
    "steps": [{
        "question": "Which region has the highest revenue?",
        "chart_type": "bar",
        "code": "print(df.groupby('region')['revenue'].sum())",
        "attempts": 1, "first_pass_success": True, "success": True,
        "stdout": "North 9000.00\nSouth 4000.00",
        "error": None,
        "charts": [{"filename": "chart_1.png", "data_b64": "aGVsbG8="}],
        "insight": "North generated 9000.00 in revenue, more than double South's 4000.00.",
        "grounding": {"total_claims": 2, "grounded_claims": 2,
                      "ungrounded": [], "accuracy": 1.0},
    }],
    "metrics": {"questions_total": 1, "questions_succeeded": 1,
                "first_pass_success_rate": 1.0, "final_success_rate": 1.0,
                "total_coder_attempts": 1, "claims_total": 3,
                "claims_grounded": 3, "grounding_accuracy": 1.0},
}


def test_render_html_contains_key_content():
    html = render_html(SAMPLE_PAYLOAD)
    assert "<title>Test Report</title>" in html
    assert "Which region drives revenue?" in html
    assert "North generated 9000.00" in html
    assert "data:image/png;base64,aGVsbG8=" in html
    assert "verified" in html
    assert "Invest in the North region." in html


def test_render_html_failed_step():
    payload = dict(SAMPLE_PAYLOAD)
    payload["steps"] = [{**SAMPLE_PAYLOAD["steps"][0], "success": False,
                         "error": "Boom", "insight": None, "charts": [],
                         "grounding": None}]
    html = render_html(payload)
    assert "analysis failed" in html
    assert "Boom" in html
