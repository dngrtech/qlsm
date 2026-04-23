# User Management & API Keys

QLSM supports multiple users. User management and API keys are both found in **Settings**.

## Users

### Create A User

1. Go to **Settings → Users**.
2. Click **Add User**.
3. Set username and password.
4. Submit.

The new user can log in immediately with the credentials you set.

### Delete A User

1. Go to **Settings → Users**.
2. Find the user and click **Delete**.

You cannot delete the currently logged-in user.

### Reset A Password

1. Go to **Settings → Users**.
2. Find the user and click **Reset Password**.
3. Enter and confirm the new password.

## API Keys

The external REST API uses Bearer token authentication, separate from the session cookie used by the UI. API keys are managed in **Settings → API Keys**.

### Create An API Key

1. Go to **Settings → API Keys**.
2. Click **Generate Key**.
3. Copy the key — it will not be shown again.

### Revoke An API Key

1. Go to **Settings → API Keys**.
2. Click **Delete** next to the key you want to remove.

## External REST API

The API is available at `/api/v1/`. It is intended for external integrations (stats bots, dashboards, Discord bots, etc.).

**Authentication:**
```
Authorization: Bearer <your_api_key>
```

**Available endpoint:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/instances` | GET | List all instances |

Rate limit: 200 requests per minute. Sensitive fields (ZMQ credentials, logs) are excluded from the response.

## Related Pages

- [Deploy A New Instance](../getting-started/deploy-new-instance.md)
