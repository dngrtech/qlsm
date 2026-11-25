import React, { useEffect, useState, useCallback } from 'react';
import { getPresets, deletePreset, checkAllPresetPluginUpdates } from '../services/api'; // Import API functions
import { useNavigate } from 'react-router-dom';
import PresetPluginUpdatesModal from '../components/presetManager/PresetPluginUpdatesModal';

function PresetsPage() {
  const [presets, setPresets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  // { [presetId]: number of outdated plugin files }; empty until the check returns.
  const [pluginUpdateCounts, setPluginUpdateCounts] = useState({});
  const [pluginUpdatesPreset, setPluginUpdatesPreset] = useState(null);
  const navigate = useNavigate();

  const fetchPluginUpdateCounts = useCallback(async () => {
    try {
      const results = await checkAllPresetPluginUpdates();
      const counts = {};
      (results || []).forEach(r => { counts[r.preset_id] = (r.plugin_changes || []).length; });
      setPluginUpdateCounts(counts);
    } catch {
      // Non-fatal: the presets list works without the update badges.
    }
  }, []);

  const fetchPresets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getPresets();
      setPresets(data || []);
    } catch (err) {
      console.error("Error fetching presets:", err);
      setError(err.message || 'Failed to fetch presets.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPresets();
    fetchPluginUpdateCounts();
  }, [fetchPresets, fetchPluginUpdateCounts]);

  const handleDeletePreset = async (presetId, presetName) => {
    if (window.confirm(`Are you sure you want to delete the preset "${presetName}"?`)) {
      try {
        await deletePreset(presetId);
        alert(`Preset "${presetName}" deleted successfully.`);
        fetchPresets(); // Refresh the list
      } catch (err) {
        console.error("Error deleting preset:", err);
        alert(`Failed to delete preset: ${err.message || 'Unknown error'}`);
        setError(err.message || 'Failed to delete preset.');
      }
    }
  };

  if (loading) return <div className="text-center p-4">Loading presets...</div>;
  if (error) return <div className="text-center p-4 text-red-500">Error: {error}</div>;

  return (
    <div className="container mx-auto p-4">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-gray-800 dark:text-white">Configuration Presets</h1>
        <button
          onClick={() => navigate('/presets/add')}
          className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline"
        >
          Add New Preset
        </button>
      </div>

      {presets.length === 0 ? (
        <p className="text-gray-600 dark:text-gray-400">No presets found. Add one to get started!</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {presets.map(preset => (
            <div key={preset.id} className="bg-white dark:bg-gray-800 shadow-lg rounded-lg p-6">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">{preset.name}</h2>
              <p className="text-gray-700 dark:text-gray-300 mb-4">{preset.description || 'No description.'}</p>
              <div className="flex justify-end space-x-2">
                {preset.is_builtin ? (
                  <span className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                    Built-in
                  </span>
                ) : (
                  <>
                    <button
                      onClick={() => setPluginUpdatesPreset({ id: preset.id, name: preset.name })}
                      className="text-sm bg-blue-500 hover:bg-blue-600 text-white font-semibold py-1 px-3 rounded"
                      title="Compare this preset's plugin files with the plugin pool"
                    >
                      {pluginUpdateCounts[preset.id] > 0
                        ? `Plugin Updates (${pluginUpdateCounts[preset.id]})`
                        : 'Plugin Updates'}
                    </button>
                    <button
                      onClick={() => navigate(`/presets/edit/${preset.id}`)}
                      className="text-sm bg-yellow-500 hover:bg-yellow-600 text-white font-semibold py-1 px-3 rounded"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDeletePreset(preset.id, preset.name)}
                      className="text-sm bg-red-500 hover:bg-red-600 text-white font-semibold py-1 px-3 rounded"
                    >
                      Delete
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <PresetPluginUpdatesModal
        isOpen={pluginUpdatesPreset !== null}
        onClose={() => setPluginUpdatesPreset(null)}
        preset={pluginUpdatesPreset}
        onApplied={fetchPluginUpdateCounts}
      />
    </div>
  );
}

export default PresetsPage;
