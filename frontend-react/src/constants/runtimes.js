// The minqlx runtime a host builds and runs. Chosen when the host is created
// and immutable afterwards -- moving a live host between runtimes is
// destructive, so QLSM offers no edit path. Mirrors ui/runtime.py.
export const DEFAULT_RUNTIME = 'minqlx';

export const RUNTIME_OPTIONS = [
  {
    id: 'minqlx',
    name: 'minqlx',
    description: 'The original runtime. Debian 12, and every plugin QLSM ships today.',
  },
  {
    id: 'minqlxtended',
    name: 'minqlxtended',
    description: 'The tjone270 fork. Ubuntu 24.04 and Python 3.12. Plugins are not interchangeable with minqlx.',
  },
];

const KNOWN = new Set(RUNTIME_OPTIONS.map(option => option.id));

// A host with no recorded runtime predates the column, and nothing but minqlx
// has ever existed.
export const runtimeLabel = (value) => (KNOWN.has(value) ? value : DEFAULT_RUNTIME);

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
// ui/routes/draft_routes.py -- the two must not drift.
const DEFAULT_PRESET_BY_RUNTIME = {
  minqlx: 'default',
  minqlxtended: 'default-minqlxtended',
};

export function defaultPresetNameForRuntime(runtime) {
  const key = typeof runtime === 'string' ? runtime.trim().toLowerCase() : '';
  return DEFAULT_PRESET_BY_RUNTIME[key] || DEFAULT_PRESET_BY_RUNTIME.minqlx;
}
