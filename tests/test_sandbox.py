"""Sandbox security + functionality tests. No LLM calls — pure executor tests."""
from sandbox.executor import run_code


def test_basic_pandas_analysis(sample_dataset):
    result = run_code(
        "total = df['revenue'].sum()\nprint(f'total_revenue = {total:.2f}')",
        sample_dataset,
    )
    assert result.success, result.error
    assert "total_revenue = 18750.00" in result.stdout


def test_blocked_import_os(sample_dataset):
    result = run_code("import os\nprint(os.listdir('/'))", sample_dataset)
    assert not result.success
    assert "blocked" in (result.error or "").lower()


def test_blocked_import_subprocess(sample_dataset):
    result = run_code("import subprocess\nsubprocess.run(['whoami'])", sample_dataset)
    assert not result.success
    assert "blocked" in (result.error or "").lower()


def test_network_disabled(sample_dataset):
    # socket import is blocked at the allowlist; even indirect socket use fails
    result = run_code("import socket\nsocket.socket()", sample_dataset)
    assert not result.success


def test_open_outside_workdir_blocked(sample_dataset, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("s3cret")
    result = run_code(f"print(open({str(secret)!r}).read())", sample_dataset)
    assert not result.success
    assert "PermissionError" in (result.error or "") or "blocked" in (result.error or "")


def test_wall_clock_timeout(sample_dataset):
    result = run_code("while True:\n    pass", sample_dataset, timeout=8)
    assert not result.success
    assert "timed out" in (result.error or "").lower()


def test_chart_collection(sample_dataset):
    code = (
        "df.groupby('region')['revenue'].sum().plot(kind='bar', title='Revenue by region')\n"
        "plt.savefig('chart_1.png', dpi=80, bbox_inches='tight')\n"
        "plt.close()\n"
        "print('chart saved')"
    )
    result = run_code(code, sample_dataset)
    assert result.success, result.error
    assert len(result.charts) == 1
    assert result.charts[0]["filename"] == "chart_1.png"
    assert len(result.charts[0]["data_b64"]) > 100


def test_runtime_error_reported(sample_dataset):
    result = run_code("print(df['no_such_column'].mean())", sample_dataset)
    assert not result.success
    assert "no_such_column" in (result.error or "")
