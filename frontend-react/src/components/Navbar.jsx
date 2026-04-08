import { Fragment } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { Menu, Transition } from '@headlessui/react';
import ThemeToggleButton from './ThemeToggleButton';
import { useAuth } from '../contexts/AuthContext';
import { Settings, Users, ChevronDown, Terminal, LogOut, Server, SlidersHorizontal, Menu as MenuIcon } from 'lucide-react';

function Navbar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, currentUser, logoutContext } = useAuth();
  const passwordChangeRequired = currentUser?.passwordChangeRequired === true;

  const handleLogout = async () => {
    await logoutContext();
    navigate('/login');
  };

  const isActive = (path) => {
    if (path === '') return location.pathname === '/';
    return location.pathname.startsWith(`/${path}`);
  };

  return (
    <nav className="navbar-container">
      {/* Layered background system */}
      <div className="navbar-bg-base" />
      <div className="navbar-grid-pattern" />
      <div className="navbar-accent-top" />
      <div className="navbar-accent-bottom" />

      <div className="navbar-content">
        {/* Left section: Branding + Status */}
        <div className="navbar-section-left">
          {/* Logo with holographic container */}
          <Link
            to={passwordChangeRequired ? '/change-password' : '/'}
            className="navbar-brand-link"
          >
            <div className="navbar-brand-icon-wrapper">
              <div className="navbar-brand-icon-glow" />
              <div className="navbar-brand-icon-bg" />
              <Terminal className="navbar-brand-icon" strokeWidth={2.5} />
            </div>
            <div className="navbar-brand-text-wrapper">
              <span className="navbar-brand-text">QLSM</span>
              <span className="navbar-brand-subtitle">Quake Live Server Management</span>
            </div>
          </Link>

        </div>

        {/* Center section: Navigation (authenticated only) */}
        {isAuthenticated && !passwordChangeRequired && (
          <div className="navbar-section-center">
            <Link
              to="/servers"
              className={`navbar-nav-link ${isActive('servers') ? 'navbar-nav-link-active' : ''}`}
            >
              <Server size={16} strokeWidth={2} />
              <span>SERVERS</span>
            </Link>

            {/* Settings dropdown */}
            <Menu as="div" className="navbar-dropdown-wrapper">
              <Menu.Button className="navbar-nav-link navbar-dropdown-trigger">
                <Settings size={16} strokeWidth={2} />
                <span>SETTINGS</span>
                <ChevronDown size={12} className="navbar-dropdown-chevron" />
              </Menu.Button>

              <Transition
                as={Fragment}
                enter="navbar-dropdown-enter"
                enterFrom="navbar-dropdown-enter-from"
                enterTo="navbar-dropdown-enter-to"
                leave="navbar-dropdown-leave"
                leaveFrom="navbar-dropdown-leave-from"
                leaveTo="navbar-dropdown-leave-to"
              >
                <Menu.Items className="navbar-dropdown-menu">
                  <div className="navbar-dropdown-accent" />
                  <div className="navbar-dropdown-content">
                    <Menu.Item>
                      {({ active }) => (
                        <Link
                          to="/settings/users"
                          className={`navbar-dropdown-item ${active ? 'navbar-dropdown-item-active' : ''}`}
                        >
                          <Users size={16} strokeWidth={2} />
                          <span>User Management</span>
                        </Link>
                      )}
                    </Menu.Item>
                    <Menu.Item>
                      {({ active }) => (
                        <Link
                          to="/settings"
                          className={`navbar-dropdown-item ${active ? 'navbar-dropdown-item-active' : ''}`}
                        >
                          <SlidersHorizontal size={16} strokeWidth={2} />
                          <span>API Settings</span>
                        </Link>
                      )}
                    </Menu.Item>
                  </div>
                </Menu.Items>
              </Transition>
            </Menu>
          </div>
        )}

        {/* Right section: Auth + Theme */}
        <div className="navbar-section-right">
          {isAuthenticated && !passwordChangeRequired && (
            <Menu as="div" className="navbar-mobile-menu-wrapper">
              <Menu.Button className="navbar-mobile-menu-trigger" aria-label="Open navigation menu">
                <MenuIcon size={18} strokeWidth={2.2} />
              </Menu.Button>

              <Transition
                as={Fragment}
                enter="navbar-dropdown-enter"
                enterFrom="navbar-dropdown-enter-from"
                enterTo="navbar-dropdown-enter-to"
                leave="navbar-dropdown-leave"
                leaveFrom="navbar-dropdown-leave-from"
                leaveTo="navbar-dropdown-leave-to"
              >
                <Menu.Items className="navbar-mobile-menu-panel">
                  <div className="navbar-dropdown-accent" />
                  <div className="navbar-dropdown-content">
                    <Menu.Item>
                      {({ active }) => (
                        <Link
                          to="/servers"
                          className={`navbar-dropdown-item ${active || isActive('servers') ? 'navbar-dropdown-item-active' : ''}`}
                        >
                          <Server size={16} strokeWidth={2} />
                          <span>Servers</span>
                        </Link>
                      )}
                    </Menu.Item>
                    <Menu.Item>
                      {({ active }) => (
                        <Link
                          to="/settings/users"
                          className={`navbar-dropdown-item ${active || location.pathname === '/settings/users' ? 'navbar-dropdown-item-active' : ''}`}
                        >
                          <Users size={16} strokeWidth={2} />
                          <span>User Management</span>
                        </Link>
                      )}
                    </Menu.Item>
                    <Menu.Item>
                      {({ active }) => (
                        <Link
                          to="/settings"
                          className={`navbar-dropdown-item ${active || location.pathname === '/settings' ? 'navbar-dropdown-item-active' : ''}`}
                        >
                          <SlidersHorizontal size={16} strokeWidth={2} />
                          <span>API Settings</span>
                        </Link>
                      )}
                    </Menu.Item>
                    <Menu.Item>
                      {({ active }) => (
                        <button
                          type="button"
                          onClick={handleLogout}
                          className={`navbar-dropdown-item navbar-mobile-logout ${active ? 'navbar-dropdown-item-active' : ''}`}
                        >
                          <LogOut size={16} strokeWidth={2} />
                          <span>Logout</span>
                        </button>
                      )}
                    </Menu.Item>
                  </div>
                </Menu.Items>
              </Transition>
            </Menu>
          )}

          {isAuthenticated ? (
            <button onClick={handleLogout} className="navbar-logout-btn">
              <LogOut size={16} strokeWidth={2} />
              <span>LOGOUT</span>
            </button>
          ) : (
            <Link to="/login" className="navbar-login-btn">
              <span>LOGIN</span>
            </Link>
          )}

          <div className="navbar-divider" />

          <div className="navbar-theme-wrapper">
            <ThemeToggleButton />
          </div>
        </div>
      </div>
    </nav>
  );
}

export default Navbar;
