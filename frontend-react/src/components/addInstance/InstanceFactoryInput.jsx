import React from 'react';

function InstanceFactoryInput({
  factoryTxt,
  onFactoryTxtChange,
}) {
  return (
    <div className="mt-4">
      <label htmlFor="factoryTxt" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
        factory (e.g., .factories) (Optional)
      </label>
      <textarea
        id="factoryTxt"
        value={factoryTxt}
        onChange={onFactoryTxtChange}
        rows="3"
        className="mt-1 block w-full input-class font-mono text-xs dark:bg-slate-700 dark:text-gray-200 dark:border-slate-600"
      />
    </div>
  );
}

export default InstanceFactoryInput;