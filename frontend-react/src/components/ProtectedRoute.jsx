import React from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

const ProtectedRoute = () => {
  const { isAuthenticated, currentUser, isLoadingAuth } = useAuth();
  const location = useLocation();

  if (isLoadingAuth) {
    return <div>Loading authentication status...</div>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (currentUser?.passwordChangeRequired) {
    if (location.pathname !== '/change-password') {
      return <Navigate to="/change-password" replace />;
    }
  } else if (location.pathname === '/change-password') {
    return <Navigate to="/servers" replace />;
  }

  return <Outlet />;
};

export default ProtectedRoute;
