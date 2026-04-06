import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createPreset } from '../services/api';

function AddPresetPage() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [serverCfg, setServerCfg] = useState('');
  const [mappool, setMappool] = useState('');
  const [access, setAccess] = useState('');
  const [workshop, setWorkshop] = useState('');
  const [factory, setFactory] = useState('');
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    if (!name.trim()) {
      setError('Preset name is required.');
      setSubmitting(false);
      return;
    }

    const presetData = {
      name,
      description,
      server_cfg: serverCfg,
      mappool,
      access,
      workshop,
      factory,
    };

    try {
      await createPreset(presetData);
      alert('Preset created successfully!');
      navigate('/presets');
    } catch (err) {
      console.error("Error creating preset:", err);
      setError(err.error?.message || err.message || 'Failed to create preset.');
    } finally {
      setSubmitting(false);
    }
  };

  const configFields = [
    { label: 'server.cfg', value: serverCfg, setter: setServerCfg, rows: 10 },
    { label: 'mappool.txt', value: mappool, setter: setMappool, rows: 5 },
    { label: 'access.txt', value: access, setter: setAccess, rows: 5 },
    { label: 'workshop.txt', value: workshop, setter: setWorkshop, rows: 5 },
    { label: 'factory (e.g., .factories)', value: factory, setter: setFactory, rows: 5 },
  ];

  return (
    <div className="container mx-auto p-4">
      <h1 className="text-3xl font-bold text-gray-800 dark:text-white mb-6">Add New Configuration Preset</h1>
      {error && <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-4" role="alert">{error}</div>}
      <form onSubmit={handleSubmit} className="bg-white dark:bg-gray-800 shadow-md rounded px-8 pt-6 pb-8 mb-4">
        <div className="mb-4">
          <label htmlFor="name" className="block text-gray-700 dark:text-gray-300 text-sm font-bold mb-2">
            Preset Name <span className="text-red-500">*</span>
          </label>
          <input
            id="name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 dark:text-gray-300 dark:bg-gray-700 leading-tight focus:outline-none focus:shadow-outline"
            required
          />
        </div>
        <div className="mb-6">
          <label htmlFor="description" className="block text-gray-700 dark:text-gray-300 text-sm font-bold mb-2">
            Description
          </label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows="3"
            className="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 dark:text-gray-300 dark:bg-gray-700 leading-tight focus:outline-none focus:shadow-outline"
          />
        </div>

        {configFields.map(field => (
          <div className="mb-6" key={field.label}>
            <label htmlFor={field.label} className="block text-gray-700 dark:text-gray-300 text-sm font-bold mb-2">
              {field.label}
            </label>
            <textarea
              id={field.label}
              value={field.value}
              onChange={(e) => field.setter(e.target.value)}
              rows={field.rows}
              className="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 dark:text-gray-300 dark:bg-gray-700 leading-tight focus:outline-none focus:shadow-outline font-mono text-sm"
              placeholder={`Enter content for ${field.label}...`}
            />
          </div>
        ))}

        <div className="flex items-center justify-between">
          <button
            type="submit"
            disabled={submitting}
            className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline disabled:bg-blue-300"
          >
            {submitting ? 'Saving...' : 'Save Preset'}
          </button>
          <button
            type="button"
            onClick={() => navigate('/presets')}
            className="bg-gray-500 hover:bg-gray-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}

export default AddPresetPage;