from pathlib import Path


def test_babylon_smoke_contract_exists():
    root = Path(__file__).resolve().parents[1]
    contract_path = root / "contracts" / "workloads" / "babylon_smoke.md"
    assert contract_path.exists(), "BABYLON smoke contract missing."
    content = contract_path.read_text(encoding="utf-8")
    assert "BABYLON Smoke Contract" in content
    assert "scripts/logs/babylon_smoke.txt" in content
