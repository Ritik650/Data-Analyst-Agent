import sys
from pathlib import Path

import pandas as pd
import pytest

# Make repo-root imports work regardless of how pytest is invoked.
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def sample_dataset(tmp_path_factory) -> str:
    df = pd.DataFrame({
        "region": ["North", "South", "North", "East"] * 25,
        "revenue": [100.0, 200.0, 150.0, 300.0] * 25,
        "units": [1, 2, 3, 4] * 25,
    })
    path = tmp_path_factory.mktemp("data") / "dataset.csv"
    df.to_csv(path, index=False)
    return str(path)
