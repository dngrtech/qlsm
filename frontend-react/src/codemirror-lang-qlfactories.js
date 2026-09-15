import { json, jsonParseLinter } from '@codemirror/lang-json';
import { autocompletion } from '@codemirror/autocomplete';
import { getCvarCatalog } from './codemirror-lang-qlcfg';

// A .factories file is JSON: a list of factory definitions, each a set of
// cvars applied on top of a base gametype. Same language as any other JSON
// file, plus completion for the three things that are easy to get wrong -
// the key names, the base gametype, and the cvar names inside "cvars".
//
// One shared language instance so CodeMirrorEditor can recognise it and add
// the completion extension (see the identity checks in that file).
export const qlFactoriesLanguage = json();
export const qlFactoriesLinterSource = () => jsonParseLinter();

// Keys of a factory definition, as used by the game's own scripts/factories.txt.
const FACTORY_KEYS = [
  ['id', 'Factory ID. This is what you pass to map <mapname> <factory> and what shows up in votes.'],
  ['title', 'Name shown to players in menus and votes.'],
  ['author', 'Who wrote the factory. Free text.'],
  ['description', 'Short description shown next to the title.'],
  ['basegt', 'Base gametype this factory builds on, for example ca or ctf.'],
  ['cvars', 'Cvars applied when a match starts with this factory. Values are strings.'],
  ['tags', 'Optional list of tags, for example ["classic"].'],
];

// Fallback list, used only until the catalog arrives from the backend.
const FALLBACK_GAMETYPES = ['ad', 'ca', 'ctf', 'dom', 'duel', 'ffa', 'ft', 'har', 'oneflag', 'race', 'rr', 'tdm'];

function renderInfo(description, sourceNote, examples) {
  return () => {
    const root = document.createElement('div');
    root.className = 'cm-cvar-info';
    const add = (text, className) => {
      if (!text) return;
      const line = document.createElement('div');
      if (className) line.className = className;
      line.textContent = text;
      root.appendChild(line);
    };
    add(description, 'cm-cvar-info-description');
    if (examples?.length) add(`Used by factories: ${examples.join(', ')}`, 'cm-cvar-info-meta');
    add(sourceNote, 'cm-cvar-info-source');
    return root;
  };
}

// Where in the JSON the cursor sits, worked out by scanning the text rather
// than by parsing: half-typed factory files are not valid JSON, and that is
// exactly when completion has to work.
export function jsonContextAt(text, pos) {
  const stack = [];
  let inString = false;
  let escaped = false;
  let buffer = '';
  let lastString = null;
  let pendingKey = null;

  for (let i = 0; i < pos; i += 1) {
    const ch = text[i];
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === '"') { inString = false; lastString = buffer; }
      else buffer += ch;
      continue;
    }
    if (ch === '"') { inString = true; escaped = false; buffer = ''; continue; }
    if (ch === '{' || ch === '[') { stack.push({ open: ch, key: pendingKey }); pendingKey = null; continue; }
    if (ch === '}' || ch === ']') { stack.pop(); pendingKey = null; continue; }
    if (ch === ':') { pendingKey = lastString; continue; }
    if (ch === ',') { pendingKey = null; continue; }
  }

  const top = [...stack].reverse().find(frame => frame.open === '{');
  return { objectKey: top ? top.key : null, depth: stack.length };
}

function cvarOptions(prefix) {
  const catalog = getCvarCatalog();
  const lower = prefix.toLowerCase();
  return catalog.cvars
    .filter(entry => entry.name.toLowerCase().includes(lower))
    .map(entry => ({
      label: entry.name,
      detail: entry.factory ? 'factory cvar' : (entry.group || 'cvar'),
      type: 'property',
      // Cvars the game's own factories actually set come first: those are the
      // ones that belong in a factory rather than in server.cfg.
      boost: (entry.factory ? 50 : 0) + (entry.name.toLowerCase().startsWith(lower) ? 10 : 0),
      info: renderInfo(
        entry.description || 'No description recorded for this cvar.',
        catalog.sources?.[entry.source] ? `Source: ${catalog.sources[entry.source]}.` : null,
        entry.examples,
      ),
    }))
    .sort((left, right) => right.boost - left.boost);
}

function gametypeOptions(prefix) {
  const catalog = getCvarCatalog();
  const gametypes = catalog.gametypes?.length ? catalog.gametypes : FALLBACK_GAMETYPES;
  const lower = prefix.toLowerCase();
  return gametypes
    .filter(name => name.toLowerCase().includes(lower))
    .map(name => ({
      label: name,
      detail: 'base gametype',
      type: 'enum',
      info: renderInfo('Base gametype used by the game\'s own factories.', 'Source: the game\'s own factory definitions.'),
    }));
}

function keyOptions(prefix) {
  const lower = prefix.toLowerCase();
  return FACTORY_KEYS
    .filter(([name]) => name.toLowerCase().includes(lower))
    .map(([name, description]) => ({
      label: name,
      detail: 'factory key',
      type: 'property',
      info: renderInfo(description, "Source: the game's own factory definitions."),
    }));
}

export function qlFactoriesCompletionSource(context) {
  // Only complete inside a string the operator is already typing, so the
  // suggestion replaces the text between the quotes and nothing else.
  const word = context.matchBefore(/"[^"\\]*/);
  if (!word) return null;

  const text = context.state.doc.toString();
  const prefix = word.text.slice(1);
  const beforeQuote = text.slice(Math.max(0, word.from - 60), word.from);
  const isValue = /:\s*$/.test(beforeQuote);
  const { objectKey } = jsonContextAt(text, word.from);

  let options = [];
  if (isValue) {
    if (/"basegt"\s*:\s*$/.test(beforeQuote)) options = gametypeOptions(prefix);
  } else if (objectKey === 'cvars') {
    options = cvarOptions(prefix);
  } else {
    options = keyOptions(prefix);
  }

  if (options.length === 0) return null;
  return { from: word.from + 1, options, filter: false };
}

export const qlFactoriesCompletion = autocompletion({ override: [qlFactoriesCompletionSource] });
