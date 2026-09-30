import json

import pytest
import yaml

from app.standards.loader import StandardLoader, get, snapshot, snapshot_hash


def test_load_all_and_api_schema():
    result = StandardLoader().load_all()
    assert set(result) == {"TECH", "MATL", "TRAIN"}
    value = result["TECH"].model_dump(by_alias=True)
    assert {"followUpOrder", "optionalFields", "subtypeFields", "commonFields", "contentHash"} <= value.keys()
    assert value["subtypeFields"]["DATA_RPT"][0]["path"] == "ext.dataDimensions"
    assert len(result["TECH"].content_hash) == 64


@pytest.mark.parametrize("change", ["duplicate", "unknown_target", "enum", "path", "regex", "kind", "length"])
def test_invalid_standard_rejected(tmp_path, change):
    value = yaml.safe_load(get("TECH").source_text)
    if change == "duplicate":
        value["elements"].append(value["elements"][0])
    elif change == "unknown_target":
        value["follow_up_order"] = ["unknown"]
    elif change == "enum":
        value["elements"][1]["options"] = {}
    elif change == "path":
        value["elements"][3]["path"] = "identity.owner"
    elif change == "regex":
        value["elements"][5]["rule"]["any_of_regex"] = ["["]
    elif change == "kind":
        value["elements"][0]["kind"] = "html"
    else:
        value["elements"][0]["rule"] = {"min_len": 10, "max_len": 3}
    (tmp_path / "tech.yaml").write_text(yaml.safe_dump(value, allow_unicode=True))
    with pytest.raises((ValueError, yaml.YAMLError)):
        StandardLoader(tmp_path).load_all()


def test_snapshot_contains_source_template_and_stable_hash():
    original = snapshot(get("TECH"))
    assert "你是 DemandHub" in original["promptTemplate"]
    assert original["standardSource"]
    assert original["rendererVersion"] == "1"
    assert snapshot_hash(original) == snapshot_hash(json.loads(json.dumps(original)))
    assert snapshot_hash(original) != snapshot_hash({**original, "rendererVersion": "2"})
