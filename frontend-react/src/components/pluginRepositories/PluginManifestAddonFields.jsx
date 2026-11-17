/**
 * The form for the selected entry of the manifest's `addons` list: the seven
 * fields ui/plugin_repositories.py _normalize_addons() reads. `id` and `zip`
 * are the only required ones; what qlsm does with a bad value is reported by
 * validateManifestAddons(), not enforced here.
 */
function PluginManifestAddonFields({ addon, onChange }) {
  const field = (key) => ({
    value: addon[key],
    onChange: (e) => onChange({ [key]: e.target.value }),
  });

  return (
    <div className="space-y-5 pb-2">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="addon-id" className="label-tech mb-1.5 block">Addon ID</label>
          <input id="addon-id" type="text" className="input-base font-mono" placeholder="my-addon" {...field('id')} />
        </div>
        <div>
          <label htmlFor="addon-label" className="label-tech mb-1.5 block">Label</label>
          <input id="addon-label" type="text" className="input-base" {...field('label')} />
        </div>
      </div>
      <div>
        <label htmlFor="addon-description" className="label-tech mb-1.5 block">Description</label>
        <textarea id="addon-description" className="input-base" rows={2} {...field('description')} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="addon-zip" className="label-tech mb-1.5 block">Zip</label>
          <input id="addon-zip" type="text" className="input-base font-mono" placeholder="my-addon.zip" {...field('zip')} />
        </div>
        <div>
          <label htmlFor="addon-version" className="label-tech mb-1.5 block">Version</label>
          <input id="addon-version" type="text" className="input-base font-mono" placeholder="1.0.0" {...field('version')} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="addon-sha256" className="label-tech mb-1.5 block">SHA-256 of the zip</label>
          <input id="addon-sha256" type="text" className="input-base font-mono text-xs" spellCheck={false} {...field('sha256')} />
        </div>
        <div>
          <label htmlFor="addon-requires" className="label-tech mb-1.5 block">Requires qlsm version</label>
          <input id="addon-requires" type="text" className="input-base font-mono" placeholder="1.36.0" {...field('requires_qlsm_version')} />
        </div>
      </div>
      <p className="text-xs text-[var(--text-muted)]">
        The zip&apos;s own <code>qlsm-addon.json</code> must use the same id, or qlsm refuses to install it.
        Installing an addon gives it full access to qlsm, so only list addons you would run yourself.
      </p>
    </div>
  );
}

export default PluginManifestAddonFields;
