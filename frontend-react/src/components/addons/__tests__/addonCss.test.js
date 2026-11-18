import { afterEach, describe, expect, it } from 'vitest';
import { addonCssPathFor, ensureAddonCss } from '../addonCss';

afterEach(() => {
  document.querySelectorAll('[id^="qlsm-addon-css--"]').forEach((el) => el.remove());
});

describe('addonCssPathFor', () => {
  it('derives the css path next to a .js component', () => {
    expect(addonCssPathFor('ui/Panel.js')).toBe('ui/Panel.css');
  });

  it('is case-insensitive about the .js extension', () => {
    expect(addonCssPathFor('ui/Panel.JS')).toBe('ui/Panel.css');
  });

  it('returns null for a non-.js component', () => {
    expect(addonCssPathFor('ui/Panel.mjs')).toBeNull();
    expect(addonCssPathFor(undefined)).toBeNull();
  });
});

describe('ensureAddonCss', () => {
  it('imports the addon css into the low-priority addon layer', () => {
    ensureAddonCss('demo-addon', 'ui/Panel.js');

    const style = document.getElementById('qlsm-addon-css--demo-addon--ui/Panel.css');
    expect(style).not.toBeNull();
    expect(style.tagName).toBe('STYLE');
    expect(style.textContent).toBe(
      '@import url("/api/addons/demo-addon/ui/ui/Panel.css") layer(qlsm-addons);',
    );
  });

  it('does not duplicate the link on a second mount of the same component', () => {
    ensureAddonCss('demo-addon', 'ui/Panel.js');
    ensureAddonCss('demo-addon', 'ui/Panel.js');

    const links = document.querySelectorAll('[id="qlsm-addon-css--demo-addon--ui/Panel.css"]');
    expect(links.length).toBe(1);
  });

  it('does nothing when the component has no css by convention', () => {
    ensureAddonCss('demo-addon', 'ui/Panel');
    expect(document.querySelectorAll('[id^="qlsm-addon-css--"]').length).toBe(0);
  });

  it('removes the import if the css fails to load', () => {
    ensureAddonCss('demo-addon', 'ui/Missing.js');
    const link = document.getElementById('qlsm-addon-css--demo-addon--ui/Missing.css');
    expect(link).not.toBeNull();

    link.onerror();

    expect(document.getElementById('qlsm-addon-css--demo-addon--ui/Missing.css')).toBeNull();
  });
});
