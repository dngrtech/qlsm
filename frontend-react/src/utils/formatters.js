const VULTR_REGIONS_DATA = `
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
`;

const VULTR_PLANS_DATA = `
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
`;

let _VULTR_REGIONS_MAP = {};
let _VULTR_PLANS_MAP = {};

function _parse_vultr_regions() {
  if (Object.keys(_VULTR_REGIONS_MAP).length > 0) { // Avoid re-parsing
    return;
  }
  const regions = {};
  const lines = VULTR_REGIONS_DATA.trim().split('\n');
  if (lines.length <= 1) return;

  const knownContinents = ['Europe', 'North America', 'Asia', 'Africa', 'Australia', 'South America'];

  for (let i = 1; i < lines.length; i++) { // Skip header
    const parts = lines[i].split(/\s+/); // Split by one or more spaces
    if (parts.length >= 4) {
      const region_id = parts[0];
      let city_parts = [];
      let continent_name = null;
      let country_code_index = -1;

      // Find country code (always 2 uppercase letters)
      for (let j = 1; j < parts.length; j++) {
        if (parts[j].length === 2 && parts[j] === parts[j].toUpperCase()) {
          country_code_index = j;
          break;
        }
      }

      if (country_code_index > 0) {
        city_parts = parts.slice(1, country_code_index);
        
        // Find continent
        let continent_parts_index = country_code_index + 1;
        for (let k = 0; k < knownContinents.length; k++) {
            const continentCandidate = knownContinents[k];
            if (parts.slice(continent_parts_index).join(" ").startsWith(continentCandidate)) {
                continent_name = continentCandidate;
                break;
            }
        }
      }
      
      if (region_id && city_parts.length > 0 && continent_name) {
        const city_name = city_parts.join(" ");
        regions[region_id] = { city: city_name, continent: continent_name };
      } else {
        console.warn(`Warning: Could not parse region line: ${lines[i]}`);
      }
    }
  }
  _VULTR_REGIONS_MAP = regions;
}


function _parse_vultr_plans() {
  if (Object.keys(_VULTR_PLANS_MAP).length > 0) { // Avoid re-parsing
    return;
  }

  const plans = {};
  const lines = VULTR_PLANS_DATA.trim().split('\n');
  if (lines.length <= 1) return; // No data or only header

  for (let i = 1; i < lines.length; i++) { // Skip header
    const parts = lines[i].split(/\s+/); // Split by one or more spaces
    if (parts.length >= 7) {
      const plan_id = parts[0];
      const vcpu_count = parts[1];
      const ram_mb = parseInt(parts[2], 10); // RAM is in MB
      const disk_gb = parts[3];
      
      // Convert RAM to GB for display, round to nearest 0.5GB or integer
      let ram_display;
      if (ram_mb < 1024) {
        ram_display = `${ram_mb} MB`;
      } else {
        const ram_gb = ram_mb / 1024;
        if (ram_gb % 1 === 0) {
            ram_display = `${ram_gb} GB`;
        } else {
            ram_display = `${ram_gb.toFixed(1)} GB`;
        }
      }

      plans[plan_id] = { 
        vcpu: vcpu_count, 
        ram: ram_display, // Use formatted RAM
        disk: `${disk_gb} GB` // Add GB suffix to disk
      };
    } else {
      if (parts.length > 0 && !parts[parts.length -1].startsWith('[')) {
         console.warn(`Warning: Could not parse plan line: ${lines[i]}`);
      }
    }
  }
  _VULTR_PLANS_MAP = plans;
}

export function formatVultrRegion(regionCode) {
  if (Object.keys(_VULTR_REGIONS_MAP).length === 0) {
    _parse_vultr_regions();
  }
  const regionInfo = _VULTR_REGIONS_MAP[regionCode];
  if (regionInfo) {
    return `${regionInfo.continent} – ${regionInfo.city}`;
  }
  return regionCode; // Return original code if not found
}

export function formatVultrPlan(planId) {
  if (Object.keys(_VULTR_PLANS_MAP).length === 0) {
    _parse_vultr_plans();
  }

  const planInfo = _VULTR_PLANS_MAP[planId];
  if (planInfo) {
    return `${planInfo.vcpu} vCPU, ${planInfo.ram} RAM, ${planInfo.disk} Storage`;
  }
  return planId; // Return original ID if not found
}

export const VULTR_REGION_TIMEZONE_MAP = {
  ams: 'Europe/Amsterdam',
  atl: 'America/New_York',
  blr: 'Asia/Kolkata',
  bom: 'Asia/Kolkata',
  cdg: 'Europe/Paris',
  del: 'Asia/Kolkata',
  dfw: 'America/Chicago',
  ewr: 'America/New_York',
  fra: 'Europe/Berlin',
  hnl: 'Pacific/Honolulu',
  icn: 'Asia/Seoul',
  itm: 'Asia/Tokyo',
  jnb: 'Africa/Johannesburg',
  lax: 'America/Los_Angeles',
  lhr: 'Europe/London',
  mad: 'Europe/Madrid',
  man: 'Europe/London',
  mel: 'Australia/Melbourne',
  mex: 'America/Mexico_City',
  mia: 'America/New_York',
  nrt: 'Asia/Tokyo',
  ord: 'America/Chicago',
  sao: 'America/Sao_Paulo',
  scl: 'America/Santiago',
  sea: 'America/Los_Angeles',
  sgp: 'Asia/Singapore',
  sjc: 'America/Los_Angeles',
  sto: 'Europe/Stockholm',
  syd: 'Australia/Sydney',
  tlv: 'Asia/Jerusalem',
  waw: 'Europe/Warsaw',
  yto: 'America/Toronto',
};

export function getTimezoneForRegion(regionCode) {
  return VULTR_REGION_TIMEZONE_MAP[regionCode] || null;
}

export const STANDALONE_TIMEZONES = [
  'Africa/Johannesburg',
  'America/Anchorage',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Mexico_City',
  'America/New_York',
  'America/Sao_Paulo',
  'America/Santiago',
  'America/Toronto',
  'Asia/Colombo',
  'Asia/Dubai',
  'Asia/Jakarta',
  'Asia/Jerusalem',
  'Asia/Kolkata',
  'Asia/Riyadh',
  'Asia/Seoul',
  'Asia/Shanghai',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Australia/Melbourne',
  'Australia/Perth',
  'Australia/Sydney',
  'Europe/Amsterdam',
  'Europe/Berlin',
  'Europe/London',
  'Europe/Madrid',
  'Europe/Moscow',
  'Europe/Paris',
  'Europe/Stockholm',
  'Europe/Warsaw',
  'Pacific/Auckland',
  'Pacific/Honolulu',
  'UTC',
];

export function formatStatus(statusString) {
  if (!statusString) return '';
  if (statusString === 'provisioned_pending_setup') {
    return 'Deploying';
  }
  return statusString
    .replace(/_/g, ' ') // Replace underscores with spaces
    .toLowerCase()
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1)) // Capitalize each word
    .join(' ');
}
// Initialize maps on module load
_parse_vultr_regions();
_parse_vultr_plans();
