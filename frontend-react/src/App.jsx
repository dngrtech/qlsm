import { Routes, Route, Navigate } from 'react-router-dom';
import AppFooter from './components/AppFooter';
import Navbar from './components/Navbar';
import { NotificationProvider } from './components/NotificationProvider';
import { LoadingProvider } from './contexts/LoadingContext';
import { AuthProvider } from './contexts/AuthContext';
import LoginPage from './pages/LoginPage';
import PresetsPage from './pages/PresetsPage';
import AddPresetPage from './pages/AddPresetPage';
import EditPresetPage from './pages/EditPresetPage';
import UserManagementPage from './pages/UserManagementPage';
import OperatorsPage from './pages/OperatorsPage';
import PluginRepositoriesPage from './pages/PluginRepositoriesPage';
import SettingsPage from './pages/SettingsPage';
import ServersPage from './pages/ServersPage';
import GlobalRconPage from './pages/GlobalRconPage';
import HostLogsPage from './pages/HostLogsPage';
import DocsPage from './pages/DocsPage';
import ChangePasswordPage from './pages/ChangePasswordPage';
import BackupRestorePage from './pages/BackupRestorePage';
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
                  <Route path="/global-rcon" element={<GlobalRconPage />} />
                  <Route path="/host-logs" element={<HostLogsPage />} />
                  <Route path="/host-logs/:hostId" element={<HostLogsPage />} />
                  <Route path="/presets" element={<PresetsPage />} />
                  <Route path="/presets/add" element={<AddPresetPage />} />
                  <Route path="/presets/edit/:presetId" element={<EditPresetPage />} />
                  <Route path="/docs/*" element={<DocsPage />} />
                  <Route path="/settings/users" element={<UserManagementPage />} />
                  <Route path="/settings/operators" element={<OperatorsPage />} />
                  <Route path="/settings/plugin-repositories" element={<PluginRepositoriesPage />} />
                  <Route path="/settings/backup" element={<BackupRestorePage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                </Route>
              </Routes>
            </main>
            <AppFooter />
          </div>
        </NotificationProvider>
      </LoadingProvider>
    </AuthProvider>
  )
}

export default App
