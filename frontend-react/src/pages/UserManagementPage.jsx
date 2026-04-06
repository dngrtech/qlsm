import React, { useState, useEffect, useCallback } from 'react';
import { UserPlus, Key, Trash2, Users, AlertCircle, Loader2 } from 'lucide-react';
import { getUsers, createUser, resetUserPassword, deleteUser } from '../services/api';
import { useNotification } from '../components/NotificationProvider';
import { useAuth } from '../contexts/AuthContext';
import ConfirmationModal from '../components/ConfirmationModal';
import AddUserModal from '../components/users/AddUserModal';
import ResetPasswordModal from '../components/users/ResetPasswordModal';
import { formatDateTime } from '../utils/uiUtils';

function UserManagementPage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [isAddUserModalOpen, setIsAddUserModalOpen] = useState(false);
  const [isResetPasswordModalOpen, setIsResetPasswordModalOpen] = useState(false);
  const [selectedUserForReset, setSelectedUserForReset] = useState(null);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [selectedUserForDelete, setSelectedUserForDelete] = useState(null);

  const { showSuccess, showError } = useNotification();
  const { user: currentUser } = useAuth();

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getUsers();
      setUsers(data || []);
    } catch (err) {
      console.error('Error fetching users:', err);
      setError(err.error?.message || err.message || 'Failed to fetch users.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleCreateUser = async (userData) => {
    await createUser(userData);
    showSuccess(`User "${userData.username}" created successfully.`);
    fetchUsers();
  };

  const handleResetPassword = async (userId, newPassword) => {
    await resetUserPassword(userId, newPassword);
    showSuccess('Password reset successfully.');
    fetchUsers();
  };

  const handleDeleteUser = async () => {
    if (!selectedUserForDelete) return;
    try {
      await deleteUser(selectedUserForDelete.id);
      showSuccess(`User "${selectedUserForDelete.username}" deleted successfully.`);
      fetchUsers();
    } catch (err) {
      showError(err.error?.message || err.message || 'Failed to delete user.');
    }
    setIsDeleteModalOpen(false);
    setSelectedUserForDelete(null);
  };

  const openResetPasswordModal = (user) => {
    setSelectedUserForReset(user);
    setIsResetPasswordModalOpen(true);
  };

  const openDeleteModal = (user) => {
    setSelectedUserForDelete(user);
    setIsDeleteModalOpen(true);
  };

  if (error) {
    return (
      <div className="users-page">
        <div className="users-page-header">
          <div className="users-page-title-row">
            <div className="users-page-title-wrapper">
              <Users className="users-page-title-icon" strokeWidth={2} />
              <h1 className="users-page-title">User Management</h1>
            </div>
          </div>
        </div>
        <div className="users-error-state">
          <AlertCircle size={24} strokeWidth={2} style={{ color: 'var(--accent-danger)' }} />
          <p className="users-error-text">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="users-page">
      {/* Page header */}
      <div className="users-page-header">
        <div className="users-page-title-row">
          <div className="users-page-title-wrapper">
            <Users className="users-page-title-icon" strokeWidth={2} />
            <h1 className="users-page-title">User Management</h1>
            {!loading && (
              <span className="users-page-count">{users.length}</span>
            )}
          </div>
          <button
            onClick={() => setIsAddUserModalOpen(true)}
            className="users-add-btn"
          >
            <UserPlus size={18} strokeWidth={2} />
            <span>Add User</span>
          </button>
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <div className="users-loading-state">
          <Loader2 className="users-loading-spinner" strokeWidth={2} />
          <span className="users-loading-text">Loading users...</span>
        </div>
      ) : users.length === 0 ? (
        <div className="users-empty-state">
          <Users size={32} strokeWidth={1.5} className="users-empty-icon" />
          <p className="users-empty-text">No users found.</p>
        </div>
      ) : (
        <div className="users-table-container">
          <table className="users-table">
            <thead>
              <tr>
                <th className="users-th">Username</th>
                <th className="users-th">Created</th>
                <th className="users-th">Last Login</th>
                <th className="users-th users-th-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id} className="users-tr">
                  <td className="users-td">
                    <span className="users-td-username">{user.username}</span>
                    {currentUser?.username === user.username && (
                      <span className="users-td-you-badge">you</span>
                    )}
                  </td>
                  <td className="users-td">
                    <span className="users-td-date">{formatDateTime(user.created_at)}</span>
                  </td>
                  <td className="users-td">
                    <span className="users-td-date">
                      {user.last_login_at ? formatDateTime(user.last_login_at) : 'Never'}
                    </span>
                  </td>
                  <td className="users-td users-td-actions">
                    <button
                      onClick={() => openResetPasswordModal(user)}
                      className="users-action-btn users-action-btn-reset"
                      title="Reset Password"
                    >
                      <Key size={16} strokeWidth={2} />
                    </button>
                    <button
                      onClick={() => openDeleteModal(user)}
                      disabled={currentUser?.username === user.username}
                      className={`users-action-btn ${
                        currentUser?.username === user.username
                          ? 'users-action-btn-disabled'
                          : 'users-action-btn-delete'
                      }`}
                      title={currentUser?.username === user.username ? 'Cannot delete yourself' : 'Delete User'}
                    >
                      <Trash2 size={16} strokeWidth={2} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <AddUserModal
        isOpen={isAddUserModalOpen}
        onClose={() => setIsAddUserModalOpen(false)}
        onSubmit={handleCreateUser}
      />

      <ResetPasswordModal
        isOpen={isResetPasswordModalOpen}
        onClose={() => {
          setIsResetPasswordModalOpen(false);
          setSelectedUserForReset(null);
        }}
        onSubmit={handleResetPassword}
        user={selectedUserForReset}
      />

      {selectedUserForDelete && (
        <ConfirmationModal
          isOpen={isDeleteModalOpen}
          onClose={() => {
            setIsDeleteModalOpen(false);
            setSelectedUserForDelete(null);
          }}
          onConfirm={handleDeleteUser}
          title="Delete User"
          message={`Are you sure you want to delete user "${selectedUserForDelete.username}"? This action cannot be undone.`}
          confirmButtonText="Delete"
          confirmButtonVariant="danger"
        />
      )}
    </div>
  );
}

export default UserManagementPage;
