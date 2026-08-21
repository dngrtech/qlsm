// The runtime a host with no recorded value is understood to be running. This
// is a *label* fallback for host rows that predate the runtime column -- it is
// deliberately NOT the Add Host form's starting value. That form starts with
// nothing selected, because the choice is immutable once the host is created
// and QLSM will not make an irreversible pick on the operator's behalf.
// Mirrors ui/runtime.py.
export const DEFAULT_RUNTIME = 'minqlx';

export const RUNTIME_OPTIONS = [
  {
    id: 'minqlx',
    name: 'minqlx',
    description: 'The original Quake Live server runtime. Every plugin QLSM ships today is written for it.',
    repoUrl: 'https://github.com/MinoMino/minqlx',
  },
  {
    id: 'minqlxtended',
    name: 'minqlxtended',
    description: 'A hard fork by tjone270. Its plugins are not interchangeable with minqlx.',
    repoUrl: 'https://github.com/tjone270/minqlxtended',
  },
];

const KNOWN = new Set(RUNTIME_OPTIONS.map(option => option.id));

// A host with no recorded runtime predates the column, and nothing but minqlx
// has ever existed.
export const runtimeLabel = (value) => (KNOWN.has(value) ? value : DEFAULT_RUNTIME);

// The closing line of a runtime's tooltip, which depends on who supplies the
// machine. On a cloud host QLSM writes the OS image, so the operator cannot get
// this wrong. On a standalone or self host the OS is already whatever it is,
// and minqlxtended is compiled on the host against libpython3.12
// (ansible/playbooks/setup_host.yml:665) -- so it needs a distro whose python3
// is already 3.12. Naming the distro rather than the Python version is
// deliberate: Debian 12 has no python3.12 in its archive, so "install Python
// 3.12" is a dead end and "use Ubuntu 24.04" is the actionable instruction.
const TOOLTIP_TAILS = {
  minqlx: {
    provisioned: 'QLSM provisions Debian 12.',
    // min_python is None for minqlx -- it runs on whatever python3 ships.
    operatorOwned: "Runs on the distro's own python3 — no version floor.",
  },
  minqlxtended: {
    provisioned: 'QLSM provisions Ubuntu 24.04.',
    // _validate_runtime_python() rejects the submission before the host row exists.
    standalone: 'Needs Ubuntu 24.04 or newer. Checked before the host is created.',
    // No pre-check exists for self: the playbook assert fails during setup and
    // the host lands in Error, with deleting it the only way back.
    self: "Needs Ubuntu 24.04 or newer. Not checked up front — setup fails if it isn't.",
  },
};

export function runtimeTooltipTail(runtime, provider) {
  const tails = TOOLTIP_TAILS[runtimeLabel(runtime)];
  if (provider !== 'standalone' && provider !== 'self') return tails.provisioned;
  return tails[provider] || tails.operatorOwned;
}

// The live (unrotated) log filename each runtime writes. Mirrors
// runtime_paths()['log_filename'] in ui/runtime.py. Used only to seed a log
// viewer's initial file selection before the backend's own file listing
// arrives -- that listing is always the source of truth once it does, and
// nothing here filters or rejects entries it returns.
const RUNTIME_LOG_FILENAMES = {
  minqlx: 'minqlx.log',
  minqlxtended: 'minqlxtended.log',
};

export const runtimeLogFilename = (value) => RUNTIME_LOG_FILENAMES[runtimeLabel(value)];

// The builtin preset a new instance seeds from, per host runtime. Plugins are
// not interchangeable between runtimes, so seeding from the wrong one ships
// files that cannot load. Mirrors _DEFAULT_PRESET_BY_RUNTIME in
// ui/preset_support.py -- the two must not drift.
const DEFAULT_PRESET_BY_RUNTIME = {
  minqlx: 'default',
  minqlxtended: 'default-minqlxtended',
};

export function defaultPresetNameForRuntime(runtime) {
  const key = typeof runtime === 'string' ? runtime.trim().toLowerCase() : '';
  return DEFAULT_PRESET_BY_RUNTIME[key] || DEFAULT_PRESET_BY_RUNTIME.minqlx;
}
