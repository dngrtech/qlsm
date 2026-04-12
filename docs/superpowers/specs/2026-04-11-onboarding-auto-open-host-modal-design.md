# Design: Auto-Open Add Host Modal on First Deployment

**Date:** 2026-04-11  
**Status:** Approved

## Summary

When a user completes the mandatory password change on a fresh QLSM deployment and is redirected to `/servers`, the Add New Host modal opens automatically if no hosts exist. This surfaces the next logical action without requiring the user to find the button themselves.

## Trigger Scope

The auto-open is tied exclusively to the post-password-change redirect. It does **not** fire on arbitrary navigation to `/servers` with no hosts. This avoids a nagging UX while still covering the primary first-deployment onboarding flow.

## Data Flow

1. User submits new password successfully in `ChangePasswordPage`
2. `navigate('/servers', { replace: true, state: { openAddHost: true } })` passes a route state flag
3. `ServersPage` mounts and reads `useLocation().state?.openAddHost`
4. Route state is cleared immediately via `window.history.replaceState({}, '')` to prevent re-triggering on page refresh
5. A `useEffect` watching `[loading, serversData]` fires once `loading === false` and `serversData.length === 0` and the flag was set — calls `setIsAddHostModalOpen(true)`
6. The existing `AddHostModal` opens normally with provider selection (self / standalone / vultr)

## Files Changed

| File | Change |
|------|--------|
| `frontend-react/src/pages/ChangePasswordPage.jsx` | Add `state: { openAddHost: true }` to the existing `navigate()` call |
| `frontend-react/src/pages/ServersPage.jsx` | Import `useLocation`, read route state flag, clear it, add one `useEffect` to auto-open the modal |

## Edge Cases

- **User already has hosts:** `serversData.length > 0` — modal does not open
- **Data fetch error:** `loading` stays in error state — modal does not open
- **Page refresh after redirect:** Route state cleared on mount — modal does not re-open
- **User closes modal without adding a host:** Normal close behaviour — modal does not re-open on next navigation

## What Is Not Changing

- The `AddHostModal` component itself is unchanged
- No localStorage, no new context, no new components
- The empty-state UI on `/servers` (the "No servers found" card with its own Add button) remains as a fallback
