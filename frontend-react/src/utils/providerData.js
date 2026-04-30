// Contains data for cloud providers used in host creation/management.

// Per-plan region availability buckets, sourced from Vultr /v2/plans.
// vc2 / vhf share the same regional footprint (no hnl, no mxp).
// vhp-amd is offered in mxp but not hnl. vhp-intel is offered in hnl but not mxp.
const FAMILY_LABELS = {
  'vc2':       'Cloud Compute (Shared)',
  'vhf':       'High Frequency',
  'vhp-amd':   'High Performance (AMD)',
  'vhp-intel': 'High Performance (Intel)',
};

function planName(family, vcpu, ram_mb, price_usd) {
  const label = FAMILY_LABELS[family] ?? family;
  const ramGb = ram_mb / 1024;
  const price = price_usd % 1 === 0 ? price_usd : price_usd.toFixed(2);
  return `${label} — ${vcpu} vCPU / ${ramGb} GB RAM / $${price}/mo`;
}

const LOC_VC2_VHF =['ams','atl','blr','bom','cdg','del','dfw','ewr','fra','icn','itm','jnb','lax','lhr','mad','man','mel','mex','mia','nrt','ord','sao','scl','sea','sgp','sjc','sto','syd','tlv','waw','yto'];
const LOC_VHP_AMD = ['ams','atl','blr','bom','cdg','del','dfw','ewr','fra','icn','itm','jnb','lax','lhr','mad','man','mel','mex','mia','mxp','nrt','ord','sao','scl','sea','sgp','sjc','sto','syd','tlv','waw','yto'];
const LOC_VHP_INTEL = ['ams','atl','blr','bom','cdg','del','dfw','ewr','fra','hnl','icn','itm','jnb','lax','lhr','mad','man','mel','mex','mia','nrt','ord','sao','scl','sea','sgp','sjc','sto','syd','tlv','waw','yto'];

export const providerOptions = {
    vultr: {
      regions: [
        { id: 'ams', city: 'Amsterdam', country: 'NL', continent: 'Europe' },
        { id: 'atl', city: 'Atlanta', country: 'US', continent: 'North America' },
        { id: 'blr', city: 'Bangalore', country: 'IN', continent: 'Asia' },
        { id: 'bom', city: 'Mumbai', country: 'IN', continent: 'Asia' },
        { id: 'cdg', city: 'Paris', country: 'FR', continent: 'Europe' },
        { id: 'del', city: 'Delhi NCR', country: 'IN', continent: 'Asia' },
        { id: 'dfw', city: 'Dallas', country: 'US', continent: 'North America' },
        { id: 'ewr', city: 'New Jersey', country: 'US', continent: 'North America' },
        { id: 'fra', city: 'Frankfurt', country: 'DE', continent: 'Europe' },
        { id: 'hnl', city: 'Honolulu', country: 'US', continent: 'North America' },
        { id: 'icn', city: 'Seoul', country: 'KR', continent: 'Asia' },
        { id: 'itm', city: 'Osaka', country: 'JP', continent: 'Asia' },
        { id: 'jnb', city: 'Johannesburg', country: 'ZA', continent: 'Africa' },
        { id: 'lax', city: 'Los Angeles', country: 'US', continent: 'North America' },
        { id: 'lhr', city: 'London', country: 'GB', continent: 'Europe' },
        { id: 'mad', city: 'Madrid', country: 'ES', continent: 'Europe' },
        { id: 'man', city: 'Manchester', country: 'GB', continent: 'Europe' },
        { id: 'mel', city: 'Melbourne', country: 'AU', continent: 'Australia' },
        { id: 'mex', city: 'Mexico City', country: 'MX', continent: 'North America' },
        { id: 'mia', city: 'Miami', country: 'US', continent: 'North America' },
        { id: 'mxp', city: 'Milan', country: 'IT', continent: 'Europe' },
        { id: 'nrt', city: 'Tokyo', country: 'JP', continent: 'Asia' },
        { id: 'ord', city: 'Chicago', country: 'US', continent: 'North America' },
        { id: 'sao', city: 'São Paulo', country: 'BR', continent: 'South America' },
        { id: 'scl', city: 'Santiago', country: 'CL', continent: 'South America' },
        { id: 'sea', city: 'Seattle', country: 'US', continent: 'North America' },
        { id: 'sgp', city: 'Singapore', country: 'SG', continent: 'Asia' },
        { id: 'sjc', city: 'Silicon Valley', country: 'US', continent: 'North America' },
        { id: 'sto', city: 'Stockholm', country: 'SE', continent: 'Europe' },
        { id: 'syd', city: 'Sydney', country: 'AU', continent: 'Australia' },
        { id: 'tlv', city: 'Tel Aviv', country: 'IL', continent: 'Asia' },
        { id: 'waw', city: 'Warsaw', country: 'PL', continent: 'Europe' },
        { id: 'yto', city: 'Toronto', country: 'CA', continent: 'North America' }
      ],
      // NOTE: Mirrors ui/vultr_plans.py. Tests assert parity.
      sizes: [
        { id: 'vhf-1c-1gb', name: planName('vhf', 1, 1024, 6), family: 'vhf', vcpu: 1, ram_mb: 1024, disk_gb: 32, bandwidth_gb: 1024, price_usd: 6.00, locations: LOC_VC2_VHF },
        { id: 'vhf-1c-2gb', name: planName('vhf', 1, 2048, 12), family: 'vhf', vcpu: 1, ram_mb: 2048, disk_gb: 64, bandwidth_gb: 2048, price_usd: 12.00, locations: LOC_VC2_VHF },
        { id: 'vhf-2c-2gb', name: planName('vhf', 2, 2048, 18), family: 'vhf', vcpu: 2, ram_mb: 2048, disk_gb: 80, bandwidth_gb: 3072, price_usd: 18.00, locations: LOC_VC2_VHF },
        { id: 'vhf-2c-4gb', name: planName('vhf', 2, 4096, 24), family: 'vhf', vcpu: 2, ram_mb: 4096, disk_gb: 128, bandwidth_gb: 3072, price_usd: 24.00, locations: LOC_VC2_VHF },
        { id: 'vhf-3c-8gb', name: planName('vhf', 3, 8192, 48), family: 'vhf', vcpu: 3, ram_mb: 8192, disk_gb: 256, bandwidth_gb: 4096, price_usd: 48.00, locations: LOC_VC2_VHF },
        { id: 'vc2-1c-1gb', name: planName('vc2', 1, 1024, 5), family: 'vc2', vcpu: 1, ram_mb: 1024, disk_gb: 25, bandwidth_gb: 1024, price_usd: 5.00, locations: LOC_VC2_VHF },
        { id: 'vc2-1c-2gb', name: planName('vc2', 1, 2048, 10), family: 'vc2', vcpu: 1, ram_mb: 2048, disk_gb: 55, bandwidth_gb: 2048, price_usd: 10.00, locations: LOC_VC2_VHF },
        { id: 'vc2-2c-2gb', name: planName('vc2', 2, 2048, 15), family: 'vc2', vcpu: 2, ram_mb: 2048, disk_gb: 65, bandwidth_gb: 3072, price_usd: 15.00, locations: LOC_VC2_VHF },
        { id: 'vc2-2c-4gb', name: planName('vc2', 2, 4096, 20), family: 'vc2', vcpu: 2, ram_mb: 4096, disk_gb: 80, bandwidth_gb: 3072, price_usd: 20.00, locations: LOC_VC2_VHF },
        { id: 'vc2-4c-8gb', name: planName('vc2', 4, 8192, 40), family: 'vc2', vcpu: 4, ram_mb: 8192, disk_gb: 160, bandwidth_gb: 4096, price_usd: 40.00, locations: LOC_VC2_VHF },
        // Overkill for QL workloads (max realistic load: 4 instances x 24 players). Re-enable if needed.
        // { id: 'vhf-4c-16gb', name: 'vhf-4c-16gb (4 VCPU, 16384 RAM, 384 DISK, 5120GB BW, $96.00/mo)', family: 'vhf', vcpu: 4, ram_mb: 16384, disk_gb: 384, bandwidth_gb: 5120, price_usd: 96.00 },
        { id: 'vhp-1c-1gb-amd', name: planName('vhp-amd', 1, 1024, 6), family: 'vhp-amd', vcpu: 1, ram_mb: 1024, disk_gb: 25, bandwidth_gb: 2048, price_usd: 6.00, locations: LOC_VHP_AMD },
        { id: 'vhp-1c-2gb-amd', name: planName('vhp-amd', 1, 2048, 12), family: 'vhp-amd', vcpu: 1, ram_mb: 2048, disk_gb: 50, bandwidth_gb: 3072, price_usd: 12.00, locations: LOC_VHP_AMD },
        { id: 'vhp-2c-2gb-amd', name: planName('vhp-amd', 2, 2048, 18), family: 'vhp-amd', vcpu: 2, ram_mb: 2048, disk_gb: 60, bandwidth_gb: 4096, price_usd: 18.00, locations: LOC_VHP_AMD },
        { id: 'vhp-2c-4gb-amd', name: planName('vhp-amd', 2, 4096, 24), family: 'vhp-amd', vcpu: 2, ram_mb: 4096, disk_gb: 100, bandwidth_gb: 5120, price_usd: 24.00, locations: LOC_VHP_AMD },
        { id: 'vhp-4c-8gb-amd', name: planName('vhp-amd', 4, 8192, 48), family: 'vhp-amd', vcpu: 4, ram_mb: 8192, disk_gb: 180, bandwidth_gb: 6144, price_usd: 48.00, locations: LOC_VHP_AMD },
        // { id: 'vhp-4c-12gb-amd', name: 'vhp-4c-12gb-amd (4 VCPU, 12288 RAM, 260 DISK, 7168GB BW, $72.00/mo)', family: 'vhp-amd', vcpu: 4, ram_mb: 12288, disk_gb: 260, bandwidth_gb: 7168, price_usd: 72.00 },
        { id: 'vhp-1c-1gb-intel', name: planName('vhp-intel', 1, 1024, 6), family: 'vhp-intel', vcpu: 1, ram_mb: 1024, disk_gb: 25, bandwidth_gb: 2048, price_usd: 6.00, locations: LOC_VHP_INTEL },
        { id: 'vhp-1c-2gb-intel', name: planName('vhp-intel', 1, 2048, 12), family: 'vhp-intel', vcpu: 1, ram_mb: 2048, disk_gb: 50, bandwidth_gb: 3072, price_usd: 12.00, locations: LOC_VHP_INTEL },
        { id: 'vhp-2c-2gb-intel', name: planName('vhp-intel', 2, 2048, 18), family: 'vhp-intel', vcpu: 2, ram_mb: 2048, disk_gb: 60, bandwidth_gb: 4096, price_usd: 18.00, locations: LOC_VHP_INTEL },
        { id: 'vhp-2c-4gb-intel', name: planName('vhp-intel', 2, 4096, 24), family: 'vhp-intel', vcpu: 2, ram_mb: 4096, disk_gb: 100, bandwidth_gb: 5120, price_usd: 24.00, locations: LOC_VHP_INTEL },
        { id: 'vhp-4c-8gb-intel', name: planName('vhp-intel', 4, 8192, 48), family: 'vhp-intel', vcpu: 4, ram_mb: 8192, disk_gb: 180, bandwidth_gb: 6144, price_usd: 48.00, locations: LOC_VHP_INTEL }
        // { id: 'vhp-4c-12gb-intel', name: 'vhp-4c-12gb-intel (4 VCPU, 12288 RAM, 260 DISK, 7168GB BW, $72.00/mo)', family: 'vhp-intel', vcpu: 4, ram_mb: 12288, disk_gb: 260, bandwidth_gb: 7168, price_usd: 72.00 },
        // Optimized Cloud (voc-*) plans omitted - designed for storage/DB workloads, overkill for QL.
        // { id: 'voc-c-1c-2gb-25s-amd', name: 'voc-c-1c-2gb-25s-amd (1 VCPU, 2048 RAM, 25 DISK, 4096GB BW, $28.00/mo)', family: 'voc-c-amd', vcpu: 1, ram_mb: 2048, disk_gb: 25, bandwidth_gb: 4096, price_usd: 28.00 },
        // { id: 'voc-g-1c-4gb-30s-amd', name: 'voc-g-1c-4gb-30s-amd (1 VCPU, 4096 RAM, 30 DISK, 4096GB BW, $30.00/mo)', family: 'voc-g-amd', vcpu: 1, ram_mb: 4096, disk_gb: 30, bandwidth_gb: 4096, price_usd: 30.00 },
        // { id: 'voc-m-1c-8gb-50s-amd', name: 'voc-m-1c-8gb-50s-amd (1 VCPU, 8192 RAM, 50 DISK, 5120GB BW, $40.00/mo)', family: 'voc-m-amd', vcpu: 1, ram_mb: 8192, disk_gb: 50, bandwidth_gb: 5120, price_usd: 40.00 },
        // { id: 'voc-c-2c-4gb-50s-amd', name: 'voc-c-2c-4gb-50s-amd (2 VCPU, 4096 RAM, 50 DISK, 5120GB BW, $40.00/mo)', family: 'voc-c-amd', vcpu: 2, ram_mb: 4096, disk_gb: 50, bandwidth_gb: 5120, price_usd: 40.00 },
        // { id: 'voc-g-2c-8gb-50s-amd', name: 'voc-g-2c-8gb-50s-amd (2 VCPU, 8192 RAM, 50 DISK, 5120GB BW, $60.00/mo)', family: 'voc-g-amd', vcpu: 2, ram_mb: 8192, disk_gb: 50, bandwidth_gb: 5120, price_usd: 60.00 },
        // { id: 'voc-c-2c-4gb-75s-amd', name: 'voc-c-2c-4gb-75s-amd (2 VCPU, 4096 RAM, 75 DISK, 5120GB BW, $45.00/mo)', family: 'voc-c-amd', vcpu: 2, ram_mb: 4096, disk_gb: 75, bandwidth_gb: 5120, price_usd: 45.00 },
        // { id: 'voc-c-4c-8gb-75s-amd', name: 'voc-c-4c-8gb-75s-amd (4 VCPU, 8192 RAM, 75 DISK, 6144GB BW, $80.00/mo)', family: 'voc-c-amd', vcpu: 4, ram_mb: 8192, disk_gb: 75, bandwidth_gb: 6144, price_usd: 80.00 },
        // { id: 'voc-g-4c-16gb-80s-amd', name: 'voc-g-4c-16gb-80s-amd (4 VCPU, 16384 RAM, 80 DISK, 6144GB BW, $120.00/mo)', family: 'voc-g-amd', vcpu: 4, ram_mb: 16384, disk_gb: 80, bandwidth_gb: 6144, price_usd: 120.00 },
        // { id: 'voc-m-2c-16gb-100s-amd', name: 'voc-m-2c-16gb-100s-amd (2 VCPU, 16384 RAM, 100 DISK, 6144GB BW, $80.00/mo)', family: 'voc-m-amd', vcpu: 2, ram_mb: 16384, disk_gb: 100, bandwidth_gb: 6144, price_usd: 80.00 },
        // { id: 'voc-s-1c-8gb-150s-amd', name: 'voc-s-1c-8gb-150s-amd (1 VCPU, 8192 RAM, 150 DISK, 4096GB BW, $75.00/mo)', family: 'voc-s-amd', vcpu: 1, ram_mb: 8192, disk_gb: 150, bandwidth_gb: 4096, price_usd: 75.00 },
        // { id: 'voc-c-4c-8gb-150s-amd', name: 'voc-c-4c-8gb-150s-amd (4 VCPU, 8192 RAM, 150 DISK, 6144GB BW, $90.00/mo)', family: 'voc-c-amd', vcpu: 4, ram_mb: 8192, disk_gb: 150, bandwidth_gb: 6144, price_usd: 90.00 },
        // { id: 'voc-m-2c-16gb-200s-amd', name: 'voc-m-2c-16gb-200s-amd (2 VCPU, 16384 RAM, 200 DISK, 6144GB BW, $100.00/mo)', family: 'voc-m-amd', vcpu: 2, ram_mb: 16384, disk_gb: 200, bandwidth_gb: 6144, price_usd: 100.00 }
      ],
    },
    linode: { // Placeholder for Linode if needed later
      continents: [],
      regions: [],
      sizes: []
    },
    standalone: {
      // Standalone servers are user-provided, no cloud provisioning
      regions: [],
      sizes: [],
      osTypes: [
        { id: 'debian', name: 'Debian' },
        { id: 'ubuntu', name: 'Ubuntu' }
      ]
    },
    self: {
      regions: [],
      sizes: [],
      osTypes: []
    }
  };

export function getPlan(providerId, planId) {
    const provider = providerOptions[providerId];
    if (!provider?.sizes) return null;
    return provider.sizes.find(plan => plan.id === planId) || null;
}

function isAvailableInRegion(plan, regionId) {
    if (!regionId) return true;
    if (!plan.locations) return true;
    return plan.locations.includes(regionId);
}

export function isValidUpgrade(providerId, currentPlanId, newPlanId, regionId = null) {
    const current = getPlan(providerId, currentPlanId);
    const next = getPlan(providerId, newPlanId);
    if (!current || !next) return false;
    if (current.family !== next.family) return false;
    if (!isAvailableInRegion(next, regionId)) return false;
    return next.price_usd > current.price_usd;
}

export function getPlansForRegion(providerId, regionId) {
    const provider = providerOptions[providerId];
    if (!provider?.sizes) return [];
    return provider.sizes.filter(plan => isAvailableInRegion(plan, regionId));
}

export function getUpgradeOptions(providerId, currentPlanId, regionId = null) {
    const provider = providerOptions[providerId];
    const current = getPlan(providerId, currentPlanId);
    if (!provider?.sizes || !current) return [];

    return provider.sizes
        .filter(plan =>
            plan.family === current.family
            && plan.price_usd > current.price_usd
            && isAvailableInRegion(plan, regionId)
        )
        .sort((a, b) => a.price_usd - b.price_usd);
}
