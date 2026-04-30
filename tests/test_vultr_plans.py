"""Tests for the Vultr plan catalog."""
import re
from pathlib import Path

from ui.vultr_plans import VULTR_PLANS, PLANS_BY_ID, get_plan, is_valid_upgrade


def test_plans_have_unique_ids():
    ids = [plan["id"] for plan in VULTR_PLANS]
    assert len(ids) == len(set(ids))


def test_every_plan_has_required_fields():
    required = {
        "id",
        "name",
        "family",
        "vcpu",
        "ram_mb",
        "disk_gb",
        "bandwidth_gb",
        "price_usd",
    }
    for plan in VULTR_PLANS:
        assert required.issubset(plan.keys()), f"Plan {plan.get('id')} missing fields"
        assert plan["family"], plan["id"]
        assert plan["vcpu"] > 0
        assert plan["ram_mb"] > 0
        assert plan["disk_gb"] > 0
        assert plan["bandwidth_gb"] > 0
        assert plan["price_usd"] > 0


def test_plans_by_id_lookup():
    plan = PLANS_BY_ID["vc2-1c-2gb"]
    assert plan["family"] == "vc2"
    assert plan["vcpu"] == 1
    assert plan["ram_mb"] == 2048


def test_get_plan_returns_none_for_unknown():
    assert get_plan("does-not-exist") is None


def test_is_valid_upgrade_same_family_higher_price():
    assert is_valid_upgrade("vc2-1c-1gb", "vc2-2c-4gb") is True


def test_is_valid_upgrade_rejects_same_plan():
    assert is_valid_upgrade("vc2-1c-2gb", "vc2-1c-2gb") is False


def test_is_valid_upgrade_rejects_downgrade():
    assert is_valid_upgrade("vc2-2c-4gb", "vc2-1c-1gb") is False


def test_is_valid_upgrade_rejects_cross_family():
    assert is_valid_upgrade("vc2-1c-2gb", "vhf-2c-4gb") is False


def test_is_valid_upgrade_rejects_unknown_plan():
    assert is_valid_upgrade("vc2-1c-2gb", "made-up-plan") is False
    assert is_valid_upgrade("made-up-plan", "vc2-1c-2gb") is False


def test_vhp_amd_and_intel_are_separate_families():
    assert is_valid_upgrade("vhp-1c-1gb-amd", "vhp-1c-2gb-intel") is False
    assert is_valid_upgrade("vhp-1c-1gb-amd", "vhp-2c-4gb-amd") is True


def test_voc_subtypes_are_separate_families():
    assert is_valid_upgrade("voc-c-1c-2gb-25s-amd", "voc-g-1c-4gb-30s-amd") is False
    assert is_valid_upgrade("voc-c-1c-2gb-25s-amd", "voc-c-2c-4gb-50s-amd") is True


def test_js_and_python_catalogs_have_identical_families():
    """Family must match between backend and frontend or upgrade options diverge."""
    js_path = Path(__file__).parent.parent / "frontend-react" / "src" / "utils" / "providerData.js"
    js_text = js_path.read_text()
    js_entries = dict(re.findall(r"id:\s*'([a-z0-9-]+)'.*?family:\s*'([a-z0-9-]+)'", js_text))
    for plan in VULTR_PLANS:
        assert js_entries.get(plan["id"]) == plan["family"], (
            f"Family mismatch for {plan['id']}: py={plan['family']}, js={js_entries.get(plan['id'])}"
        )


def test_js_and_python_catalogs_have_identical_ids():
    """Guard against backend/frontend plan catalog drift."""
    js_path = Path(__file__).parent.parent / "frontend-react" / "src" / "utils" / "providerData.js"
    js_text = js_path.read_text()
    js_ids = set(re.findall(r"id:\s*'([a-z0-9-]+)'", js_text))
    py_ids = {plan["id"] for plan in VULTR_PLANS}

    js_plan_ids = {
        plan_id
        for plan_id in js_ids
        if plan_id in py_ids or plan_id.startswith(("vc2-", "vhf-", "vhp-", "voc-"))
    }
    assert py_ids == js_plan_ids, f"Drift: only-in-py={py_ids - js_plan_ids}, only-in-js={js_plan_ids - py_ids}"
