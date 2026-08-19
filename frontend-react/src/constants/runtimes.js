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
