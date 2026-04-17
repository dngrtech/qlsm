import { Routes, Route, Navigate } from 'react-router-dom';
import Navbar from './components/Navbar';
import { NotificationProvider } from './components/NotificationProvider';
import { LoadingProvider } from './contexts/LoadingContext';
import { AuthProvider } from './contexts/AuthContext';
import LoginPage from './pages/LoginPage';
import PresetsPage from './pages/PresetsPage';
import AddPresetPage from './pages/AddPresetPage';
import EditPresetPage from './pages/EditPresetPage';
import UserManagementPage from './pages/UserManagementPage';
import SettingsPage from './pages/SettingsPage';
import ServersPage from './pages/ServersPage';
import ChangePasswordPage from './pages/ChangePasswordPage';
import ProtectedRoute from './components/ProtectedRoute';

function App() {
  return (
    <AuthProvider>
      <LoadingProvider>
        <NotificationProvider>
          {/* Main container uses CSS variable-based theme class */}
          <div className="app-shell flex flex-col min-h-screen bg-theme-base text-theme-primary">
            <Navbar />
            <main className="main-shell flex-grow relative z-0 main-grid-bg">
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route element={<ProtectedRoute />}>
                  <Route path="/" element={<Navigate to="/servers" replace />} />
                  <Route path="/change-password" element={<ChangePasswordPage />} />
                  <Route path="/servers" element={<ServersPage />} />
                  <Route path="/presets" element={<PresetsPage />} />
                  <Route path="/presets/add" element={<AddPresetPage />} />
                  <Route path="/presets/edit/:presetId" element={<EditPresetPage />} />
                  <Route path="/settings/users" element={<UserManagementPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                </Route>
              </Routes>
            </main>
            <footer
              className="sticky bottom-0 z-50 bg-theme-raised border-t border-theme flex items-center justify-center text-sm text-theme-secondary shrink-0"
              style={{ height: 'var(--footer-height)' }}
            >
              <span className="font-mono text-xs tracking-wide">
                QLSM — Quake Live Server Management
              </span>
            </footer>
          </div>
        </NotificationProvider>
      </LoadingProvider>
    </AuthProvider>
  )
}

export default App
