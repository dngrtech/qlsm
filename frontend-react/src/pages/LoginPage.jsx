import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { login } from '../services/auth';
import { useAuth } from '../contexts/AuthContext';
import { Shield, AlertCircle, Loader2 } from 'lucide-react';

function LoginPage() {
  const { loginContext } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const response = await login(username, password);
      if (response && response.data && response.data.message === "Login successful." && response.data.user) {
        loginContext(response.data.user);
        // Use the Credential Management API with the form element directly — this is
        // the spec-recommended, most reliable approach for prompting Edge/Chrome to save passwords.
        if (window.PasswordCredential) {
          try {
            const cred = new window.PasswordCredential(e.target);
            await navigator.credentials.store(cred);
          } catch {
            // credential save is best-effort; never block login
          }
        }
        navigate(
          response.data.user.passwordChangeRequired ? '/change-password' : '/servers',
          { replace: true }
        );
      } else {
        setError('Login failed: Unexpected response from server.');
        console.error('Login error: Unexpected response', response);
      }
    } catch (err) {
      const errorMessage = err.error?.message || err.message || 'Login failed. Please check your credentials.';
      setError(errorMessage);
      console.error('Login error:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      {/* Background layers */}
      <div className="login-bg-base" />
      <div className="login-grid-pattern" />
      <div className="login-gradient-overlay" />

      {/* Content */}
      <div className="login-content">
        {/* Login card */}
        <div className="login-card">
          {/* Accent line */}
          <div className="login-accent-top" />

          {/* Header */}
          <div className="login-header">
            {/* Logo with glow */}
            <div className="login-icon-wrapper">
              <div className="login-icon-glow" />
              <img src="/ql_logo.png" alt="Quake Live" className="login-logo-img" />
            </div>

            {/* Branding */}
            <div className="login-branding">
              <h1 className="login-title">QLSM</h1>
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="login-form">
            {/* Username field */}
            <div className="login-field">
              <label htmlFor="username" className="login-label">
                <span className="login-label-text">USERNAME</span>
              </label>
              <div className="login-input-wrapper">
                <input
                  id="username"
                  name="username"
                  type="text"
                  autoComplete="username"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="login-input"
                  placeholder="Enter username"
                  disabled={loading}
                />
                <div className="login-input-border" />
              </div>
            </div>

            {/* Password field */}
            <div className="login-field">
              <label htmlFor="password" className="login-label">
                <span className="login-label-text">PASSWORD</span>
              </label>
              <div className="login-input-wrapper">
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="login-input"
                  placeholder="Enter password"
                  disabled={loading}
                />
                <div className="login-input-border" />
              </div>
            </div>

            {/* Error message */}
            {error && (
              <div className="login-error">
                <AlertCircle className="login-error-icon" strokeWidth={2} />
                <div className="login-error-content">
                  <p className="login-error-title">ACCESS DENIED</p>
                  <p className="login-error-message">{error}</p>
                </div>
              </div>
            )}

            {/* Submit button */}
            <button
              type="submit"
              disabled={loading}
              className="login-submit-btn"
            >
              {loading ? (
                <>
                  <Loader2 className="login-submit-spinner" strokeWidth={2.5} />
                  <span>LOGGING IN</span>
                </>
              ) : (
                <>
                  <Shield className="login-submit-icon" strokeWidth={2.5} />
                  <span>LOGIN</span>
                </>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;
