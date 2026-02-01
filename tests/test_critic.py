"""Grounding-verification unit tests. No LLM calls — pure verify() logic."""
from agents.critic import extract_numbers, verify


def test_extract_numbers_variants():
    text = "Revenue was $1,234.56 (up 12.5%) across -3 regions; ratio 0.045."
    assert extract_numbers(text) == ["$1,234.56", "12.5%", "-3", "0.045"]


def test_exact_match_grounded():
    g = verify("The average revenue was 187.50.", "avg_revenue = 187.50")
    assert g.is_grounded and g.total_claims == 1


def test_rounded_quote_grounded():
    g = verify("Mean BMI is roughly 27.13.", "mean_bmi = 27.1284")
    assert g.is_grounded


def test_percent_fraction_equivalence():
    g = verify("About 23.5% of loans defaulted.", "default_rate = 0.235")
    assert g.is_grounded


def test_fabricated_number_flagged():
    g = verify("Revenue grew 42.7% year over year.", "total_revenue = 5000.00")
    assert not g.is_grounded
    assert "42.7%" in g.ungrounded


def test_small_integers_exempt():
    g = verify("The top 3 regions account for most sales.", "north = 900\nsouth = 850")
    assert g.total_claims == 0  # ordinal 3 is exempt


def test_question_numbers_exempt():
    g = verify("Q4 2024 revenue was 5000.00.", "revenue = 5000.00",
               exempt_text="What was revenue in Q4 2024?")
    assert g.is_grounded


def test_comma_and_currency_normalisation():
    g = verify("Total spend reached $12,500.", "total_spend = 12500.0")
    assert g.is_grounded


def test_accuracy_metric():
    g = verify("Values were 100.0 and 999.9.", "a = 100.0")
    assert g.total_claims == 2 and g.grounded_claims == 1
    assert g.accuracy == 0.5
