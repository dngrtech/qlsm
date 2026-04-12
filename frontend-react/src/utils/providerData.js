// Contains data for cloud providers used in host creation/management.

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
      sizes: [
        { id: 'vc2-1c-1gb', name: 'vc2-1c-1gb (1 VCPU, 1024 RAM, 25 DISK, 1024GB BW, $5.00/mo)' },
        { id: 'vc2-1c-2gb', name: 'vc2-1c-2gb (1 VCPU, 2048 RAM, 55 DISK, 2048GB BW, $10.00/mo)' },
        { id: 'vc2-2c-2gb', name: 'vc2-2c-2gb (2 VCPU, 2048 RAM, 65 DISK, 3072GB BW, $15.00/mo)' },
        { id: 'vc2-2c-4gb', name: 'vc2-2c-4gb (2 VCPU, 4096 RAM, 80 DISK, 3072GB BW, $20.00/mo)' },
        { id: 'vc2-4c-8gb', name: 'vc2-4c-8gb (4 VCPU, 8192 RAM, 160 DISK, 4096GB BW, $40.00/mo)' },
        { id: 'vhf-1c-1gb', name: 'vhf-1c-1gb (1 VCPU, 1024 RAM, 32 DISK, 1024GB BW, $6.00/mo)' },
        { id: 'vhf-1c-2gb', name: 'vhf-1c-2gb (1 VCPU, 2048 RAM, 64 DISK, 2048GB BW, $12.00/mo)' },
        { id: 'vhf-2c-2gb', name: 'vhf-2c-2gb (2 VCPU, 2048 RAM, 80 DISK, 3072GB BW, $18.00/mo)' },
        { id: 'vhf-2c-4gb', name: 'vhf-2c-4gb (2 VCPU, 4096 RAM, 128 DISK, 3072GB BW, $24.00/mo)' },
        { id: 'vhf-3c-8gb', name: 'vhf-3c-8gb (3 VCPU, 8192 RAM, 256 DISK, 4096GB BW, $48.00/mo)' },
        { id: 'vhf-4c-16gb', name: 'vhf-4c-16gb (4 VCPU, 16384 RAM, 384 DISK, 5120GB BW, $96.00/mo)' },
        { id: 'vhp-1c-1gb-amd', name: 'vhp-1c-1gb-amd (1 VCPU, 1024 RAM, 25 DISK, 2048GB BW, $6.00/mo)' },
        { id: 'vhp-1c-2gb-amd', name: 'vhp-1c-2gb-amd (1 VCPU, 2048 RAM, 50 DISK, 3072GB BW, $12.00/mo)' },
        { id: 'vhp-2c-2gb-amd', name: 'vhp-2c-2gb-amd (2 VCPU, 2048 RAM, 60 DISK, 4096GB BW, $18.00/mo)' },
        { id: 'vhp-2c-4gb-amd', name: 'vhp-2c-4gb-amd (2 VCPU, 4096 RAM, 100 DISK, 5120GB BW, $24.00/mo)' },
        { id: 'vhp-4c-8gb-amd', name: 'vhp-4c-8gb-amd (4 VCPU, 8192 RAM, 180 DISK, 6144GB BW, $48.00/mo)' },
        { id: 'vhp-4c-12gb-amd', name: 'vhp-4c-12gb-amd (4 VCPU, 12288 RAM, 260 DISK, 7168GB BW, $72.00/mo)' },
        { id: 'vhp-1c-1gb-intel', name: 'vhp-1c-1gb-intel (1 VCPU, 1024 RAM, 25 DISK, 2048GB BW, $6.00/mo)' },
        { id: 'vhp-1c-2gb-intel', name: 'vhp-1c-2gb-intel (1 VCPU, 2048 RAM, 50 DISK, 3072GB BW, $12.00/mo)' },
        { id: 'vhp-2c-2gb-intel', name: 'vhp-2c-2gb-intel (2 VCPU, 2048 RAM, 60 DISK, 4096GB BW, $18.00/mo)' },
        { id: 'vhp-2c-4gb-intel', name: 'vhp-2c-4gb-intel (2 VCPU, 4096 RAM, 100 DISK, 5120GB BW, $24.00/mo)' },
        { id: 'vhp-4c-8gb-intel', name: 'vhp-4c-8gb-intel (4 VCPU, 8192 RAM, 180 DISK, 6144GB BW, $48.00/mo)' },
        { id: 'vhp-4c-12gb-intel', name: 'vhp-4c-12gb-intel (4 VCPU, 12288 RAM, 260 DISK, 7168GB BW, $72.00/mo)' },
        { id: 'voc-c-1c-2gb-25s-amd', name: 'voc-c-1c-2gb-25s-amd (1 VCPU, 2048 RAM, 25 DISK, 4096GB BW, $28.00/mo)' },
        { id: 'voc-g-1c-4gb-30s-amd', name: 'voc-g-1c-4gb-30s-amd (1 VCPU, 4096 RAM, 30 DISK, 4096GB BW, $30.00/mo)' },
        { id: 'voc-m-1c-8gb-50s-amd', name: 'voc-m-1c-8gb-50s-amd (1 VCPU, 8192 RAM, 50 DISK, 5120GB BW, $40.00/mo)' },
        { id: 'voc-c-2c-4gb-50s-amd', name: 'voc-c-2c-4gb-50s-amd (2 VCPU, 4096 RAM, 50 DISK, 5120GB BW, $40.00/mo)' },
        { id: 'voc-g-2c-8gb-50s-amd', name: 'voc-g-2c-8gb-50s-amd (2 VCPU, 8192 RAM, 50 DISK, 5120GB BW, $60.00/mo)' },
        { id: 'voc-c-2c-4gb-75s-amd', name: 'voc-c-2c-4gb-75s-amd (2 VCPU, 4096 RAM, 75 DISK, 5120GB BW, $45.00/mo)' },
        { id: 'voc-c-4c-8gb-75s-amd', name: 'voc-c-4c-8gb-75s-amd (4 VCPU, 8192 RAM, 75 DISK, 6144GB BW, $80.00/mo)' },
        { id: 'voc-g-4c-16gb-80s-amd', name: 'voc-g-4c-16gb-80s-amd (4 VCPU, 16384 RAM, 80 DISK, 6144GB BW, $120.00/mo)' },
        { id: 'voc-m-2c-16gb-100s-amd', name: 'voc-m-2c-16gb-100s-amd (2 VCPU, 16384 RAM, 100 DISK, 6144GB BW, $80.00/mo)' },
        { id: 'voc-s-1c-8gb-150s-amd', name: 'voc-s-1c-8gb-150s-amd (1 VCPU, 8192 RAM, 150 DISK, 4096GB BW, $75.00/mo)' },
        { id: 'voc-c-4c-8gb-150s-amd', name: 'voc-c-4c-8gb-150s-amd (4 VCPU, 8192 RAM, 150 DISK, 6144GB BW, $90.00/mo)' },
        { id: 'voc-m-2c-16gb-200s-amd', name: 'voc-m-2c-16gb-200s-amd (2 VCPU, 16384 RAM, 200 DISK, 6144GB BW, $100.00/mo)' }
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
