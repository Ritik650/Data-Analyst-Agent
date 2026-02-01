"""Generate 8 varied synthetic datasets (seeded — fully reproducible at $0).

Each dataset gets a paired natural-language problem statement in problems.json.
Run:  python -m eval.generate_datasets
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path(__file__).parent / "test_datasets"
rng = np.random.default_rng(42)


def sales() -> pd.DataFrame:
    n = 1200
    regions = rng.choice(["North", "South", "East", "West"], n, p=[0.3, 0.2, 0.25, 0.25])
    months = rng.integers(1, 13, n)
    base = np.where(regions == "North", 5200, 3800) + months * 120
    return pd.DataFrame({
        "region": regions,
        "month": months,
        "product": rng.choice(["Widget", "Gadget", "Gizmo"], n),
        "units_sold": rng.poisson(40, n),
        "revenue": (base + rng.normal(0, 900, n)).round(2),
        "discount_pct": rng.choice([0, 5, 10, 15], n),
    })


def healthcare() -> pd.DataFrame:
    n = 900
    age = rng.integers(18, 90, n)
    smoker = rng.choice([0, 1], n, p=[0.75, 0.25])
    return pd.DataFrame({
        "patient_age": age,
        "smoker": smoker,
        "bmi": (rng.normal(27, 5, n)).round(1),
        "systolic_bp": (110 + age * 0.4 + smoker * 8 + rng.normal(0, 10, n)).round(0),
        "cholesterol": (170 + age * 0.6 + rng.normal(0, 25, n)).round(0),
        "readmitted_30d": rng.choice([0, 1], n, p=[0.85, 0.15]),
        "length_of_stay": rng.poisson(4, n) + 1,
    })


def sports() -> pd.DataFrame:
    n = 600
    minutes = rng.integers(400, 3100, n)
    return pd.DataFrame({
        "player_position": rng.choice(["GK", "DEF", "MID", "FWD"], n, p=[0.1, 0.3, 0.35, 0.25]),
        "minutes_played": minutes,
        "goals": rng.poisson(minutes / 700, n),
        "assists": rng.poisson(minutes / 900, n),
        "pass_accuracy_pct": (rng.normal(81, 7, n)).clip(40, 99).round(1),
        "tackles": rng.poisson(30, n),
        "age": rng.integers(18, 38, n),
    })


def finance() -> pd.DataFrame:
    n = 1000
    income = rng.lognormal(10.8, 0.5, n)
    score = (300 + (income / 400) + rng.normal(200, 80, n)).clip(300, 850)
    return pd.DataFrame({
        "annual_income": income.round(0),
        "credit_score": score.round(0),
        "loan_amount": (income * rng.uniform(0.1, 0.6, n)).round(0),
        "loan_term_months": rng.choice([12, 24, 36, 60], n),
        "defaulted": (score < 560).astype(int) & rng.choice([0, 1], n, p=[0.4, 0.6]),
        "employment_years": rng.integers(0, 35, n),
    })


def retail() -> pd.DataFrame:
    n = 1500
    return pd.DataFrame({
        "store_type": rng.choice(["Mall", "Street", "Online"], n, p=[0.3, 0.4, 0.3]),
        "category": rng.choice(["Apparel", "Electronics", "Home", "Beauty"], n),
        "basket_value": (rng.gamma(3, 28, n)).round(2),
        "items_per_basket": rng.poisson(3, n) + 1,
        "customer_age": rng.integers(16, 75, n),
        "is_member": rng.choice([0, 1], n, p=[0.6, 0.4]),
        "returned": rng.choice([0, 1], n, p=[0.92, 0.08]),
    })


def hr() -> pd.DataFrame:
    n = 800
    tenure = rng.integers(0, 20, n)
    return pd.DataFrame({
        "department": rng.choice(["Engineering", "Sales", "Support", "HR", "Finance"], n),
        "tenure_years": tenure,
        "salary": (45000 + tenure * 2800 + rng.normal(0, 9000, n)).round(0),
        "performance_score": rng.choice([1, 2, 3, 4, 5], n, p=[0.05, 0.15, 0.4, 0.3, 0.1]),
        "overtime_hours_month": rng.poisson(9, n),
        "attrition": rng.choice([0, 1], n, p=[0.82, 0.18]),
    })


def energy() -> pd.DataFrame:
    n = 1096  # ~3 years daily
    day = np.arange(n)
    temp = 15 + 10 * np.sin(2 * np.pi * day / 365) + rng.normal(0, 3, n)
    return pd.DataFrame({
        "day_index": day,
        "avg_temp_c": temp.round(1),
        "consumption_mwh": (900 + np.abs(temp - 18) * 22 + rng.normal(0, 40, n)).round(1),
        "is_weekend": (day % 7 >= 5).astype(int),
        "solar_generation_mwh": (np.clip(120 + 60 * np.sin(2 * np.pi * day / 365), 20, None)
                                 + rng.normal(0, 15, n)).round(1),
    })


def education() -> pd.DataFrame:
    n = 700
    study = rng.gamma(4, 2.5, n)
    return pd.DataFrame({
        "study_hours_week": study.round(1),
        "attendance_pct": (rng.normal(85, 10, n)).clip(30, 100).round(1),
        "prior_gpa": (rng.normal(3.0, 0.5, n)).clip(1.0, 4.0).round(2),
        "final_score": (40 + study * 2.2 + rng.normal(0, 8, n)).clip(0, 100).round(1),
        "extracurricular": rng.choice([0, 1], n, p=[0.55, 0.45]),
        "school_type": rng.choice(["Public", "Private", "Charter"], n, p=[0.6, 0.25, 0.15]),
    })


DATASETS = {
    "sales.csv": (sales, "Sales",
        "Which regions and months drive revenue, and how do discounts affect units sold? "
        "Recommend where to focus next quarter's sales push."),
    "healthcare.csv": (healthcare, "Healthcare",
        "What patient factors are associated with higher blood pressure and 30-day "
        "readmission? Suggest which patient groups need closer monitoring."),
    "sports.csv": (sports, "Sports",
        "How does playing time relate to goals and assists across positions, and does "
        "age matter? Identify the most productive player profiles."),
    "finance.csv": (finance, "Finance",
        "What separates borrowers who default from those who repay? Quantify the role of "
        "credit score and income, and propose lending criteria."),
    "retail.csv": (retail, "Retail",
        "Compare basket value across store types and categories, and assess whether "
        "membership changes spending or returns. Recommend a growth lever."),
    "hr.csv": (hr, "HR",
        "What drives attrition in this workforce? Examine salary, tenure, overtime and "
        "performance, and recommend retention actions."),
    "energy.csv": (energy, "Energy",
        "How does temperature drive electricity consumption, and what seasonal pattern "
        "does solar generation follow? Advise on capacity planning."),
    "education.csv": (education, "Education",
        "How strongly do study hours and attendance predict final scores across school "
        "types? Recommend the highest-impact intervention."),
}


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    problems = {}
    for filename, (builder, domain, problem) in DATASETS.items():
        df = builder()
        df.to_csv(OUT_DIR / filename, index=False)
        problems[filename] = {"domain": domain, "problem": problem}
        print(f"wrote {filename}: {len(df)} rows")
    (OUT_DIR / "problems.json").write_text(json.dumps(problems, indent=2), encoding="utf-8")
    print(f"wrote problems.json ({len(problems)} datasets)")


if __name__ == "__main__":
    main()
