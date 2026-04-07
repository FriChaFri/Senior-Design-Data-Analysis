from pathlib import Path

from imu_pipeline.requirements import load_requirement_specs


def test_load_requirement_specs_reads_authoritative_specs_sheet() -> None:
    specs = load_requirement_specs(Path("Needs+Specs.xlsx"))

    spec_ids = {spec.spec_id for spec in specs}
    assert {"F", "G", "H", "O"}.issubset(spec_ids)

    spec_o = next(spec for spec in specs if spec.spec_id == "O")
    assert spec_o.required is True
    assert "2.0 h" in spec_o.description
