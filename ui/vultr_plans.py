"""Vultr instance plan catalog known to QLSM.

This module is the backend source of truth for plan validation. The frontend
mirrors this data in frontend-react/src/utils/providerData.js, and tests assert
that both catalogs list the same plan IDs.
"""


def _family(plan_id):
    """Compatibility group for in-place upgrades.

    Plans only resize cleanly within the same hardware track, so the family
    must distinguish CPU vendor (amd/intel) and voc subtype (c/g/m/s).
    """
    parts = plan_id.split("-")
    prefix = parts[0]
    if prefix == "vhp":
        return f"vhp-{parts[-1]}"
    if prefix == "voc":
        return f"voc-{parts[1]}-{parts[-1]}"
    return prefix


def _plan(plan_id, vcpu, ram_mb, disk_gb, bandwidth_gb, price_usd):
    return {
        "id": plan_id,
        "name": (
            f"{plan_id} ({vcpu} VCPU, {ram_mb} RAM, {disk_gb} DISK, "
            f"{bandwidth_gb}GB BW, ${price_usd:.2f}/mo)"
        ),
        "family": _family(plan_id),
        "vcpu": vcpu,
        "ram_mb": ram_mb,
        "disk_gb": disk_gb,
        "bandwidth_gb": bandwidth_gb,
        "price_usd": price_usd,
    }


VULTR_PLANS = [
    # vc2: Cloud Compute
    _plan("vc2-1c-1gb", 1, 1024, 25, 1024, 5.00),
    _plan("vc2-1c-2gb", 1, 2048, 55, 2048, 10.00),
    _plan("vc2-2c-2gb", 2, 2048, 65, 3072, 15.00),
    _plan("vc2-2c-4gb", 2, 4096, 80, 3072, 20.00),
    _plan("vc2-4c-8gb", 4, 8192, 160, 4096, 40.00),

    # vhf: High Frequency
    _plan("vhf-1c-1gb", 1, 1024, 32, 1024, 6.00),
    _plan("vhf-1c-2gb", 1, 2048, 64, 2048, 12.00),
    _plan("vhf-2c-2gb", 2, 2048, 80, 3072, 18.00),
    _plan("vhf-2c-4gb", 2, 4096, 128, 3072, 24.00),
    _plan("vhf-3c-8gb", 3, 8192, 256, 4096, 48.00),
    # Overkill for QL workloads (max realistic load: 4 instances x 24 players). Re-enable if needed.
    # _plan("vhf-4c-16gb", 4, 16384, 384, 5120, 96.00),

    # vhp: High Performance (AMD)
    _plan("vhp-1c-1gb-amd", 1, 1024, 25, 2048, 6.00),
    _plan("vhp-1c-2gb-amd", 1, 2048, 50, 3072, 12.00),
    _plan("vhp-2c-2gb-amd", 2, 2048, 60, 4096, 18.00),
    _plan("vhp-2c-4gb-amd", 2, 4096, 100, 5120, 24.00),
    _plan("vhp-4c-8gb-amd", 4, 8192, 180, 6144, 48.00),
    # _plan("vhp-4c-12gb-amd", 4, 12288, 260, 7168, 72.00),

    # vhp: High Performance (Intel)
    _plan("vhp-1c-1gb-intel", 1, 1024, 25, 2048, 6.00),
    _plan("vhp-1c-2gb-intel", 1, 2048, 50, 3072, 12.00),
    _plan("vhp-2c-2gb-intel", 2, 2048, 60, 4096, 18.00),
    _plan("vhp-2c-4gb-intel", 2, 4096, 100, 5120, 24.00),
    _plan("vhp-4c-8gb-intel", 4, 8192, 180, 6144, 48.00),
    # _plan("vhp-4c-12gb-intel", 4, 12288, 260, 7168, 72.00),

    # voc: Optimized Cloud (omitted - designed for storage/DB workloads, overkill for QL)
    # _plan("voc-c-1c-2gb-25s-amd", 1, 2048, 25, 4096, 28.00),
    # _plan("voc-g-1c-4gb-30s-amd", 1, 4096, 30, 4096, 30.00),
    # _plan("voc-m-1c-8gb-50s-amd", 1, 8192, 50, 5120, 40.00),
    # _plan("voc-c-2c-4gb-50s-amd", 2, 4096, 50, 5120, 40.00),
    # _plan("voc-g-2c-8gb-50s-amd", 2, 8192, 50, 5120, 60.00),
    # _plan("voc-c-2c-4gb-75s-amd", 2, 4096, 75, 5120, 45.00),
    # _plan("voc-c-4c-8gb-75s-amd", 4, 8192, 75, 6144, 80.00),
    # _plan("voc-g-4c-16gb-80s-amd", 4, 16384, 80, 6144, 120.00),
    # _plan("voc-m-2c-16gb-100s-amd", 2, 16384, 100, 6144, 80.00),
    # _plan("voc-s-1c-8gb-150s-amd", 1, 8192, 150, 4096, 75.00),
    # _plan("voc-c-4c-8gb-150s-amd", 4, 8192, 150, 6144, 90.00),
    # _plan("voc-m-2c-16gb-200s-amd", 2, 16384, 200, 6144, 100.00),
]

PLANS_BY_ID = {plan["id"]: plan for plan in VULTR_PLANS}


def get_plan(plan_id):
    """Return the plan dict for plan_id, or None if unknown."""
    return PLANS_BY_ID.get(plan_id)


def is_valid_upgrade(current_plan_id, new_plan_id):
    """Return True when new_plan_id is a same-family, higher-price upgrade."""
    current = get_plan(current_plan_id)
    new = get_plan(new_plan_id)
    if current is None or new is None:
        return False
    if current["family"] != new["family"]:
        return False
    return new["price_usd"] > current["price_usd"]
