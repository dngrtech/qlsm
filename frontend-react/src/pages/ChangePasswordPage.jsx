import React, { useState } from 'react';
import { AlertCircle, KeyRound, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { useNotification } from '../components/NotificationProvider';
import { useAuth } from '../contexts/AuthContext';
import { changePassword } from '../services/auth';

function ChangePasswordPage() {
  const navigate = useNavigate();
  const { clearPasswordChangeRequired } = useAuth();
  const { showSuccess } = useNotification();
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await changePassword(password, confirmPassword);
      clearPasswordChangeRequired();
      showSuccess('Password updated successfully.');
      navigate('/servers', { replace: true, state: { openAddHost: true } });
    } catch (err) {
      setError(err.error?.message || err.message || 'Failed to change password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      {/* Background layers — same as login */}
      <div className="login-bg-base" />
      <div className="login-grid-pattern" />
      <div className="login-gradient-overlay" />

      {/* Content */}
      <div className="login-content">
        <div className="login-card">
          <div className="login-accent-top" />

          {/* Header */}
          <div className="login-header">
            <div className="login-icon-wrapper">
              <div className="login-icon-glow" />
              <KeyRound size={36} strokeWidth={1.8} className="login-key-icon" />
            </div>
            <div className="login-branding">
              <h1 className="login-title">NEW PASSWORD</h1>
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="login-form">
            <div className="login-field">
              <label htmlFor="new-password" className="login-label">
                <span className="login-label-text">NEW PASSWORD</span>
              </label>
              <div className="login-input-wrapper">
                <input
                  id="new-password"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="login-input"
                  placeholder="Enter new password"
                  disabled={loading}
                />
                <div className="login-input-border" />
              </div>
            </div>

            <div className="login-field">
              <label htmlFor="confirm-password" className="login-label">
                <span className="login-label-text">CONFIRM PASSWORD</span>
              </label>
              <div className="login-input-wrapper">
                <input
                  id="confirm-password"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="login-input"
                  placeholder="Retype new password"
                  disabled={loading}
                />
                <div className="login-input-border" />
              </div>
            </div>

            {error && (
              <div className="login-error">
                <AlertCircle className="login-error-icon" strokeWidth={2} />
                <div className="login-error-content">
                  <p className="login-error-title">ERROR</p>
                  <p className="login-error-message">{error}</p>
                </div>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="login-submit-btn"
            >
              {loading ? (
                <>
                  <Loader2 className="login-submit-spinner" strokeWidth={2.5} />
                  <span>UPDATING</span>
                </>
              ) : (
                <>
                  <KeyRound className="login-submit-icon" strokeWidth={2.5} />
                  <span>SAVE PASSWORD</span>
                </>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

export default ChangePasswordPage;
