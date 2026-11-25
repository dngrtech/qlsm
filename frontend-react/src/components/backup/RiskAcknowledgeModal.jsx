import React, { useState } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { AlertTriangle } from 'lucide-react';

const SENSITIVE_ITEMS = [
  'SSH private keys (full access to every managed server)',
  'Your Vultr API key (full access to your cloud account)',
  'User login credentials (password hashes)',
  'Per-instance RCON and stats passwords',
  'Addon settings, including any credentials stored in them',
  'Terraform state for every provisioned host',
];

function RiskAcknowledgeModal({ isOpen, onClose, onConfirm }) {
  const [acknowledged, setAcknowledged] = useState(false);

  const handleClose = () => {
    setAcknowledged(false);
    onClose();
  };

  const handleConfirm = () => {
    setAcknowledged(false);
    onConfirm();
  };

  return (
    <Dialog open={isOpen} as="div" className="relative z-10" onClose={handleClose}>
      <DialogBackdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0" />
      <div className="fixed inset-0 overflow-y-auto">
        <div className="flex min-h-full items-center justify-center p-4 text-center">
          <Dialog.Panel transition className="modal-panel w-full max-w-lg transform overflow-hidden p-6 text-left align-middle transition-all transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0 data-[closed]:translate-y-4 data-[closed]:scale-95">
            <div className="accent-line-top" />

            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-10 h-10 rounded-full bg-red-100 dark:bg-[#FF3366]/10 border border-red-200 dark:border-[#FF3366]/30 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-red-600 dark:text-[#FF3366]" />
              </div>
              <div className="flex-1">
                <Dialog.Title as="h3" className="font-display text-lg font-semibold tracking-wide text-theme-primary">
                  Export without a password?
                </Dialog.Title>
                <p className="mt-2 text-sm text-theme-secondary">
                  Sensitive data in the downloaded file will be readable in plain text.
                </p>
                <ul className="mt-2 text-sm text-theme-secondary list-disc pl-5 space-y-1">
                  {SENSITIVE_ITEMS.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <label className="mt-4 flex items-start gap-2 text-sm text-theme-primary">
                  <input
                    type="checkbox"
                    checked={acknowledged}
                    onChange={(e) => setAcknowledged(e.target.checked)}
                    aria-label="I understand the risk"
                  />
                  <span>I understand the risk</span>
                </label>
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <button type="button" className="btn btn-secondary" onClick={handleClose}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={!acknowledged}
                onClick={handleConfirm}
              >
                Continue
              </button>
            </div>
          </Dialog.Panel>
        </div>
      </div>
    </Dialog>
  );
}

export default RiskAcknowledgeModal;
