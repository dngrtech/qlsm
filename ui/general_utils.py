import logging
import re

log = logging.getLogger(__name__)

# --- Vultr Data (Moved from htmx_routes.py) ---

VULTR_REGIONS_DATA = """
ID      CITY            COUNTRY         CONTINENT       OPTIONS
ams     Amsterdam       NL              Europe          [ddos_protection, block_storage_storage_opt, block_storage_high_perf, load_balancers, kubernetes]
atl     Atlanta         US              North America   [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
blr     Bangalore       IN              Asia            [ddos_protection, block_storage_storage_opt, block_storage_high_perf, load_balancers, kubernetes]
bom     Mumbai          IN              Asia            [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
cdg     Paris           FR              Europe          [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
del     Delhi NCR       IN              Asia            [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
dfw     Dallas          US              North America   [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
ewr     New Jersey      US              North America   [ddos_protection, block_storage_high_perf, block_storage_storage_opt, load_balancers, kubernetes]
fra     Frankfurt       DE              Europe          [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
hnl     Honolulu       US              North America   [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
icn     Seoul           KR              Asia            [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
itm     Osaka           JP              Asia            [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
jnb     Johannesburg    ZA              Africa          [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
lax     Los Angeles     US              North America   [ddos_protection, block_storage_storage_opt, block_storage_high_perf, load_balancers, kubernetes]
lhr     London          GB              Europe          [ddos_protection, block_storage_high_perf, block_storage_storage_opt, load_balancers, kubernetes]
mad     Madrid          ES              Europe          [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
man     Manchester      GB              Europe          [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
mel     Melbourne       AU              Australia       [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
mex     Mexico City     MX              North America   [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
mia     Miami           US              North America   [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
nrt     Tokyo           JP              Asia            [ddos_protection, block_storage_high_perf, block_storage_storage_opt, load_balancers, kubernetes]
ord     Chicago         US              North America   [ddos_protection, block_storage_storage_opt, block_storage_high_perf, load_balancers, kubernetes]
sao     São Paulo       BR              South America   [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
scl     Santiago        CL              South America   [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
sea     Seattle         US              North America   [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
sgp     Singapore       SG              Asia            [ddos_protection, block_storage_storage_opt, block_storage_high_perf, load_balancers, kubernetes]
sjc     Silicon Valley  US              North America   [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
sto     Stockholm       SE              Europe          [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
syd     Sydney          AU              Australia       [ddos_protection, block_storage_high_perf, load_balancers, kubernetes]
tlv     Tel Aviv        IL              Asia            [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
waw     Warsaw          PL              Europe          [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
yto     Toronto         CA              North America   [ddos_protection, block_storage_storage_opt, load_balancers, kubernetes]
"""

VULTR_PLANS_DATA = """
ID				VCPU COUNT	RAM	DISK	DISK COUNT	BANDWIDTH GB	PRICE PER MONTH		TYPE	GPU VRAM	GPU TYPE	REGIONS
vc2-1c-1gb			1		1024	25	1		1024		5.00			vc2	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, bom, jnb, tlv, blr, del, scl, itm, man]
vc2-1c-2gb			1		2048	55	1		2048		10.00			vc2	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, bom, jnb, tlv, blr, del, scl, itm, man]
vc2-2c-2gb			2		2048	65	1		3072		15.00			vc2	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, bom, jnb, tlv, blr, del, scl, itm, man]
vc2-2c-4gb			2		4096	80	1		3072		20.00			vc2	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, bom, jnb, tlv, blr, del, scl, itm, man]
vc2-4c-8gb			4		8192	160	1		4096		40.00			vc2	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, bom, jnb, tlv, blr, del, scl, itm, man]
vhf-1c-1gb			1		1024	32	1		1024		6.00			vhf	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, bom, jnb, tlv, blr, del, scl, itm, man]
vhf-1c-2gb			1		2048	64	1		2048		12.00			vhf	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, bom, jnb, tlv, blr, del, scl, itm, man]
vhf-2c-2gb			2		2048	80	1		3072		18.00			vhf	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, bom, jnb, tlv, blr, del, scl, itm, man]
vhf-2c-4gb			2		4096	128	1		3072		24.00			vhf	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, bom, jnb, tlv, blr, del, scl, itm, man]
vhf-3c-8gb			3		8192	256	1		4096		48.00			vhf	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, bom, jnb, tlv, blr, del, scl, itm, man]
vhf-4c-16gb			4		16384	384	1		5120		96.00			vhf	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, bom, jnb, tlv, blr, del, scl, itm, man]
vhp-1c-1gb-amd			1		1024	25	1		2048		6.00			vhp	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
vhp-1c-2gb-amd			1		2048	50	1		3072		12.00			vhp	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
vhp-2c-2gb-amd			2		2048	60	1		4096		18.00			vhp	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
vhp-2c-4gb-amd			2		4096	100	1		5120		24.00			vhp	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
vhp-4c-8gb-amd			4		8192	180	1		6144		48.00			vhp	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
vhp-4c-12gb-amd			4		12288	260	1		7168		72.00			vhp	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
vhp-1c-1gb-intel		1		1024	25	1		2048		6.00			vhp	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
vhp-1c-2gb-intel		1		2048	50	1		3072		12.00			vhp	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
vhp-2c-2gb-intel		2		2048	60	1		4096		18.00			vhp	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
vhp-2c-4gb-intel		2		4096	100	1		5120		24.00			vhp	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
vhp-4c-8gb-intel		4		8192	180	1		6144		48.00			vhp	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
vhp-4c-12gb-intel		4		12288	260	1		7168		72.00			vhp	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
voc-c-1c-2gb-25s-amd		1		2048	25	1		4096		28.00			voc	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
voc-g-1c-4gb-30s-amd		1		4096	30	1		4096		30.00			voc	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
voc-m-1c-8gb-50s-amd		1		8192	50	1		5120		40.00			voc	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
voc-c-2c-4gb-50s-amd		2		4096	50	1		5120		40.00			voc	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
voc-g-2c-8gb-50s-amd		2		8192	50	1		5120		60.00			voc	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
voc-c-2c-4gb-75s-amd		2		4096	75	1		5120		45.00			voc	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
voc-c-4c-8gb-75s-amd		4		8192	75	1		6144		80.00			voc	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
voc-g-4c-16gb-80s-amd		4		16384	80	1		6144		120.00			voc	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
voc-m-2c-16gb-100s-amd		2		16384	100	1		6144		80.00			voc	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
voc-s-1c-8gb-150s-amd		1		8192	150	1		4096		75.00			voc	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
voc-c-4c-8gb-150s-amd		4		8192	150	1		6144		90.00			voc	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
voc-m-2c-16gb-200s-amd		2		16384	200	1		6144		100.00			voc	0				[ewr, ord, dfw, sea, lax, atl, ams, lhr, fra, sjc, syd, yto, cdg, nrt, waw, mad, icn, mia, sgp, sto, mex, mel, hnl, bom, jnb, tlv, blr, del, scl, itm, man]
"""

# --- Parsed Data Dictionaries (for efficient lookup) ---

_VULTR_REGIONS_MAP = {}
_VULTR_PLANS_MAP = {}

def _parse_vultr_regions():
    """Parses the VULTR_REGIONS_DATA string into a dictionary."""
    global _VULTR_REGIONS_MAP
    if _VULTR_REGIONS_MAP: # Avoid re-parsing
        return

    regions = {}
    for line in VULTR_REGIONS_DATA.strip().split('\n')[1:]: # Skip header
        parts = line.split()
        if len(parts) >= 4:
            continent_name = None
            continent_start_index = -1
            known_continents = ['Europe', 'North America', 'Asia', 'Africa', 'Australia', 'South America']
            for i in range(len(parts)):
                if parts[i] in known_continents:
                    continent_name = parts[i]
                    continent_start_index = i
                    break
                if i + 1 < len(parts) and f"{parts[i]} {parts[i+1]}" in known_continents:
                    continent_name = f"{parts[i]} {parts[i+1]}"
                    continent_start_index = i
                    break

            if continent_name and continent_start_index != -1:
                region_id = parts[0]
                city_parts = parts[1:continent_start_index - 1]
                city_name = " ".join(city_parts)
                regions[region_id] = {'city': city_name, 'continent': continent_name}
            else:
                 log.warning(f"Could not parse region line: {line}")
    _VULTR_REGIONS_MAP = regions

def _parse_vultr_plans():
    """Parses the VULTR_PLANS_DATA string into a dictionary."""
    global _VULTR_PLANS_MAP
    if _VULTR_PLANS_MAP: # Avoid re-parsing
        return

    plans = {}
    for line in VULTR_PLANS_DATA.strip().split('\n')[1:]: # Skip header
        parts = line.split()
        if len(parts) >= 7:
            plan_id = parts[0]
            vcpu_count = parts[1]
            ram = parts[2]
            disk = parts[3]
            plans[plan_id] = {'vcpu': vcpu_count, 'ram': ram, 'disk': disk}
        else:
            # Handle potential parsing issues for summary lines or unexpected formats
            if parts and not parts[-1].startswith('['): # Simple check to skip summary lines
                 log.warning(f"Could not parse plan line: {line}")
    _VULTR_PLANS_MAP = plans


# --- Formatting Functions ---

def format_vultr_region(region_code):
    """Formats a Vultr region code (e.g., 'cdg') into 'Continent – City'."""
    if not _VULTR_REGIONS_MAP:
        _parse_vultr_regions()
    
    region_info = _VULTR_REGIONS_MAP.get(region_code)
    if region_info:
        return f"{region_info['continent']} – {region_info['city']}"
    return region_code # Return original code if not found

def format_vultr_plan(plan_id):
    """Formats a Vultr plan ID (e.g., 'vc2-1c-1gb') into 'VCPU, RAM, DISK'."""
    if not _VULTR_PLANS_MAP:
        _parse_vultr_plans()

    plan_info = _VULTR_PLANS_MAP.get(plan_id)
    if plan_info:
        return f"{plan_info['vcpu']} VCPU, {plan_info['ram']} RAM, {plan_info['disk']} DISK"
    return plan_id # Return original ID if not found

# --- Other Utility Functions (if needed) ---

# Example: Sanitize workspace name (can be moved here from terraform_tasks)
def sanitize_workspace_name(name):
    """Sanitizes a host name to be suitable for a Terraform workspace name."""
    # Replace spaces and underscores with hyphens
    sanitized = name.lower().replace(' ', '-').replace('_', '-')
    # Remove any characters that are not alphanumeric or hyphen
    sanitized = re.sub('[^\\w-]', '', sanitized)
    # Ensure it doesn't start or end with a hyphen (optional, Terraform might handle this)
    sanitized = sanitized.strip('-')
    # Handle potential empty string after sanitization
    if not sanitized:
        return 'default-workspace' # Or raise an error
    return sanitized

# Initialize maps on module load
_parse_vultr_regions()
_parse_vultr_plans()
