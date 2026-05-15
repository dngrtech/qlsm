// Contains data for cloud providers used in host creation/management.

// Per-plan region availability buckets, sourced from Vultr /v2/plans API.
// vc2 / vhf share the same regional footprint (no hnl, no mxp).
// vhp-amd is offered in mxp but not hnl. vhp-intel is offered in hnl but not mxp.
// voc-c-amd is offered in both hnl and mxp (superset of vhp-amd and vhp-intel).
const FAMILY_LABELS = {
  'vc2':       'Cloud Compute — Shared',
  'vhf':       'High Frequency — Shared',
  'vhp-amd':   'High Performance — Shared (AMD)',
  'vhp-intel': 'High Performance — Shared (Intel)',
  'voc-c-amd': 'Dedicated CPU (AMD)',
};

function planName(family, vcpu, ram_mb, price_usd) {
  const label = FAMILY_LABELS[family] ?? family;
  const ramGb = ram_mb / 1024;
  const price = price_usd % 1 === 0 ? price_usd : price_usd.toFixed(2);
  return `${label} — ${vcpu} vCPU / ${ramGb} GB RAM / $${price}/mo`;
}

const LOC_VC2_VHF  = ['ams','atl','blr','bom','cdg','del','dfw','ewr','fra','icn','itm','jnb','lax','lhr','mad','man','mel','mex','mia','nrt','ord','sao','scl','sea','sgp','sjc','sto','syd','tlv','waw','yto'];
const LOC_VHP_AMD  = ['ams','atl','blr','bom','cdg','del','dfw','ewr','fra','icn','itm','jnb','lax','lhr','mad','man','mel','mex','mia','mxp','nrt','ord','sao','scl','sea','sgp','sjc','sto','syd','tlv','waw','yto'];
const LOC_VHP_INTEL= ['ams','atl','blr','bom','cdg','del','dfw','ewr','fra','hnl','icn','itm','jnb','lax','lhr','mad','man','mel','mex','mia','nrt','ord','sao','scl','sea','sgp','sjc','sto','syd','tlv','waw','yto'];
const LOC_VOC_C    = ['ams','atl','blr','bom','cdg','del','dfw','ewr','fra','hnl','icn','itm','jnb','lax','lhr','mad','man','mel','mex','mia','mxp','nrt','ord','sao','scl','sea','sgp','sjc','sto','syd','tlv','waw','yto'];

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
        { id: 'vhf-1c-1gb', name: planName('vhf', 1, 1024, 6), perfLabel: 'Low-Perf', qlCount: 1, family: 'vhf', vcpu: 1, ram_mb: 1024, disk_gb: 32, bandwidth_gb: 1024, price_usd: 6.00, locations: LOC_VC2_VHF },
        { id: 'vhf-1c-2gb', name: planName('vhf', 1, 2048, 12), perfLabel: 'Low-Perf', qlCount: 1, family: 'vhf', vcpu: 1, ram_mb: 2048, disk_gb: 64, bandwidth_gb: 2048, price_usd: 12.00, locations: LOC_VC2_VHF },
        { id: 'vhf-2c-2gb', name: planName('vhf', 2, 2048, 18), perfLabel: 'Low-Perf', qlCount: 2, family: 'vhf', vcpu: 2, ram_mb: 2048, disk_gb: 80, bandwidth_gb: 3072, price_usd: 18.00, locations: LOC_VC2_VHF },
        { id: 'vhf-2c-4gb', name: planName('vhf', 2, 4096, 24), perfLabel: 'Low-Perf', qlCount: 2, family: 'vhf', vcpu: 2, ram_mb: 4096, disk_gb: 128, bandwidth_gb: 3072, price_usd: 24.00, locations: LOC_VC2_VHF },
        { id: 'vhf-3c-8gb', name: planName('vhf', 3, 8192, 48), perfLabel: 'Low-Perf', qlCount: 3, family: 'vhf', vcpu: 3, ram_mb: 8192, disk_gb: 256, bandwidth_gb: 4096, price_usd: 48.00, locations: LOC_VC2_VHF },
        // Overkill for QL workloads (max realistic load: 4 instances x 24 players). Re-enable if needed.
        // { id: 'vhf-4c-16gb', name: 'vhf-4c-16gb (4 VCPU, 16384 RAM, 384 DISK, 5120GB BW, $96.00/mo)', family: 'vhf', vcpu: 4, ram_mb: 16384, disk_gb: 384, bandwidth_gb: 5120, price_usd: 96.00 },
        { id: 'voc-c-1c-2gb-25s-amd', name: planName('voc-c-amd', 1, 2048, 28), perfLabel: 'Hi-Perf', qlCount: 1, family: 'voc-c-amd', vcpu: 1, ram_mb: 2048, disk_gb: 25, bandwidth_gb: 4096, price_usd: 28.00, locations: LOC_VOC_C },
        { id: 'voc-c-2c-4gb-50s-amd', name: planName('voc-c-amd', 2, 4096, 40), perfLabel: 'Hi-Perf', qlCount: 2, family: 'voc-c-amd', vcpu: 2, ram_mb: 4096, disk_gb: 50, bandwidth_gb: 5120, price_usd: 40.00, locations: LOC_VOC_C },
        { id: 'voc-c-4c-8gb-75s-amd', name: planName('voc-c-amd', 4, 8192, 80), perfLabel: 'Hi-Perf', qlCount: 4, family: 'voc-c-amd', vcpu: 4, ram_mb: 8192, disk_gb: 75, bandwidth_gb: 6144, price_usd: 80.00, locations: LOC_VOC_C },
        // Other voc-* subfamilies (general-purpose, memory, storage) omitted — overkill for QL.
        { id: 'vc2-1c-1gb', name: planName('vc2', 1, 1024, 5), perfLabel: 'Low-Perf', qlCount: 1, family: 'vc2', vcpu: 1, ram_mb: 1024, disk_gb: 25, bandwidth_gb: 1024, price_usd: 5.00, locations: LOC_VC2_VHF },
        { id: 'vc2-1c-2gb', name: planName('vc2', 1, 2048, 10), perfLabel: 'Low-Perf', qlCount: 1, family: 'vc2', vcpu: 1, ram_mb: 2048, disk_gb: 55, bandwidth_gb: 2048, price_usd: 10.00, locations: LOC_VC2_VHF },
        { id: 'vc2-2c-2gb', name: planName('vc2', 2, 2048, 15), perfLabel: 'Low-Perf', qlCount: 2, family: 'vc2', vcpu: 2, ram_mb: 2048, disk_gb: 65, bandwidth_gb: 3072, price_usd: 15.00, locations: LOC_VC2_VHF },
        { id: 'vc2-2c-4gb', name: planName('vc2', 2, 4096, 20), perfLabel: 'Low-Perf', qlCount: 2, family: 'vc2', vcpu: 2, ram_mb: 4096, disk_gb: 80, bandwidth_gb: 3072, price_usd: 20.00, locations: LOC_VC2_VHF },
        { id: 'vc2-4c-8gb', name: planName('vc2', 4, 8192, 40), perfLabel: 'Low-Perf', qlCount: 4, family: 'vc2', vcpu: 4, ram_mb: 8192, disk_gb: 160, bandwidth_gb: 4096, price_usd: 40.00, locations: LOC_VC2_VHF },
        { id: 'vhp-1c-1gb-amd', name: planName('vhp-amd', 1, 1024, 6), perfLabel: 'Hi-Perf', qlCount: 1, family: 'vhp-amd', vcpu: 1, ram_mb: 1024, disk_gb: 25, bandwidth_gb: 2048, price_usd: 6.00, locations: LOC_VHP_AMD },
        { id: 'vhp-1c-2gb-amd', name: planName('vhp-amd', 1, 2048, 12), perfLabel: 'Hi-Perf', qlCount: 1, family: 'vhp-amd', vcpu: 1, ram_mb: 2048, disk_gb: 50, bandwidth_gb: 3072, price_usd: 12.00, locations: LOC_VHP_AMD },
        { id: 'vhp-2c-2gb-amd', name: planName('vhp-amd', 2, 2048, 18), perfLabel: 'Hi-Perf', qlCount: 2, family: 'vhp-amd', vcpu: 2, ram_mb: 2048, disk_gb: 60, bandwidth_gb: 4096, price_usd: 18.00, locations: LOC_VHP_AMD },
        { id: 'vhp-2c-4gb-amd', name: planName('vhp-amd', 2, 4096, 24), perfLabel: 'Hi-Perf', qlCount: 2, family: 'vhp-amd', vcpu: 2, ram_mb: 4096, disk_gb: 100, bandwidth_gb: 5120, price_usd: 24.00, locations: LOC_VHP_AMD },
        { id: 'vhp-4c-8gb-amd', name: planName('vhp-amd', 4, 8192, 48), perfLabel: 'Hi-Perf', qlCount: 4, family: 'vhp-amd', vcpu: 4, ram_mb: 8192, disk_gb: 180, bandwidth_gb: 6144, price_usd: 48.00, locations: LOC_VHP_AMD },
        // { id: 'vhp-4c-12gb-amd', name: 'vhp-4c-12gb-amd (4 VCPU, 12288 RAM, 260 DISK, 7168GB BW, $72.00/mo)', family: 'vhp-amd', vcpu: 4, ram_mb: 12288, disk_gb: 260, bandwidth_gb: 7168, price_usd: 72.00 },
        { id: 'vhp-1c-1gb-intel', name: planName('vhp-intel', 1, 1024, 6), perfLabel: 'Hi-Perf', qlCount: 1, family: 'vhp-intel', vcpu: 1, ram_mb: 1024, disk_gb: 25, bandwidth_gb: 2048, price_usd: 6.00, locations: LOC_VHP_INTEL },
        { id: 'vhp-1c-2gb-intel', name: planName('vhp-intel', 1, 2048, 12), perfLabel: 'Hi-Perf', qlCount: 1, family: 'vhp-intel', vcpu: 1, ram_mb: 2048, disk_gb: 50, bandwidth_gb: 3072, price_usd: 12.00, locations: LOC_VHP_INTEL },
        { id: 'vhp-2c-2gb-intel', name: planName('vhp-intel', 2, 2048, 18), perfLabel: 'Hi-Perf', qlCount: 2, family: 'vhp-intel', vcpu: 2, ram_mb: 2048, disk_gb: 60, bandwidth_gb: 4096, price_usd: 18.00, locations: LOC_VHP_INTEL },
        { id: 'vhp-2c-4gb-intel', name: planName('vhp-intel', 2, 4096, 24), perfLabel: 'Hi-Perf', qlCount: 2, family: 'vhp-intel', vcpu: 2, ram_mb: 4096, disk_gb: 100, bandwidth_gb: 5120, price_usd: 24.00, locations: LOC_VHP_INTEL },
        { id: 'vhp-4c-8gb-intel', name: planName('vhp-intel', 4, 8192, 48), perfLabel: 'Hi-Perf', qlCount: 4, family: 'vhp-intel', vcpu: 4, ram_mb: 8192, disk_gb: 180, bandwidth_gb: 6144, price_usd: 48.00, locations: LOC_VHP_INTEL }
        // { id: 'vhp-4c-12gb-intel', name: 'vhp-4c-12gb-intel (4 VCPU, 12288 RAM, 260 DISK, 7168GB BW, $72.00/mo)', family: 'vhp-intel', vcpu: 4, ram_mb: 12288, disk_gb: 260, bandwidth_gb: 7168, price_usd: 72.00 },
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
