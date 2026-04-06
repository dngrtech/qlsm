import React, { createContext, useContext, useState, useEffect } from 'react';
import { getAuthStatus, logout } from '../services/auth';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentUser, setCurrentUser] = useState(null); // Add state for current user
  const [isLoading, setIsLoading] = useState(true); // To handle initial auth check loading

  useEffect(() => {
    // Check auth status when the app loads
    const checkAuthStatus = async () => {
      try {
        const response = await getAuthStatus();
        if (response.data && response.data.isAuthenticated) {
          setIsAuthenticated(true);
          setCurrentUser(response.data.user);
        } else {
          setIsAuthenticated(false);
          setCurrentUser(null);
        }
      } catch {
        setIsAuthenticated(false);
        setCurrentUser(null);
      } finally {
        setIsLoading(false);
      }
    };

    checkAuthStatus();
  }, []);

  // loginContext now accepts user data from the login API response
  const loginContext = (userData) => {
    setIsAuthenticated(true);
    setCurrentUser(userData); // Store user info from login response
  };

  const logoutContext = async () => {
    try {
      await logout();
    } catch (error) {
      console.error('Backend logout failed:', error);
    } finally {
      setIsAuthenticated(false);
      setCurrentUser(null);
    }
  };

  const clearPasswordChangeRequired = () => {
    setCurrentUser((user) => (
      user ? { ...user, passwordChangeRequired: false } : user
    ));
  };

  if (isLoading) {
    // Optional: Render a loading spinner or null while checking auth status
    return null; // Or a proper spinner component
  }

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        currentUser,
        loginContext,
        logoutContext,
        clearPasswordChangeRequired,
        isLoadingAuth: isLoading,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined || context === null) { // Check for null as well
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
