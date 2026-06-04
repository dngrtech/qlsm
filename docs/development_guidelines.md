# Development Guidelines

This document outlines the version control strategy and coding practices for the QLSM project.

## Version Control Strategy

*   **Tool:** Git.
*   **Repository:** Central repository recommended (e.g., named `qlds-ui`).
*   **Branching:** Feature branching workflow (e.g., `feature/list-instances`, `feature/edit-config`, `fix/auth-bug`).

## Coding Practices & Principles

*   **Descriptive Naming:** Clear, purpose-indicating names for files, variables, functions.
*   **Cohesion:** Group related functionality together.
*   **Modularity:** Structure code into logical, focused modules/functions/classes.
*   **Clear Responsibilities:** File purpose clear from name and location.
*   **Responsive Design:** Ensure UI elements adapt gracefully to various screen sizes using Tailwind CSS utilities.

## API Response Patterns

### Success Responses
- `200 OK` - Successful GET or operation
- `201 Created` - Resource created (POST)
- `202 Accepted` - Async task queued

### Error Responses
- `400 Bad Request` - Validation failure, missing data
- `401 Unauthorized` - Authentication failure
- `404 Not Found` - Resource doesn't exist
- `409 Conflict` - Duplicate name, state conflict
- `500 Server Error` - Unexpected error

### JSON Structure
- Success: `{"data": {...}, "message": "optional"}`
- Error: `{"error": {"message": "description"}}`

## Validation Patterns

### Backend Validation Order
1. Type check (`isinstance(name, str)`)
2. Normalize (`.strip()`, `.lower()`)
3. Empty check (`if not name:`)
4. Length check (`len(name) > MAX`)
5. Pattern check (`re.match(PATTERN, name)`)
6. Uniqueness check (database lookup)

### Shared Validators
Create reusable validation functions that return `(validated_value, error_dict)`:
```python
def validate_host_name(name, exclude_id=None):
    if not isinstance(name, str):
        return None, {"message": "...", "status_code": 400}
    # ... validation steps ...
    return validated_name, None
```

### Frontend Validation
- Mirror backend validation in `frontend-react/src/utils/` (e.g., `resourceValidation.js`)
- Validate on blur and before submission
- Display errors inline below inputs with red styling

## Error Handling Patterns

### Route-Level
```python
try:
    # Main logic
except sqlalchemy.exc.IntegrityError:
    db.session.rollback()
    return jsonify({"error": {...}}), 409
except Exception as e:
    db.session.rollback()
    current_app.logger.error(f"Error: {e}", exc_info=True)
    return jsonify({"error": {...}}), 500
```

### Task-Level
- Update status to ERROR on failure
- Use `append_log()` from `task_logic/common.py`
- Always commit status changes
- Return boolean or error string (don't raise exceptions to RQ)

## Task Logic Patterns

### Structure
- Entry point: `ui/tasks.py` (decorated with `@with_app_context`)
- Logic: `ui/task_logic/*.py` (actual implementation)

### Status Flow
1. Set status to "in progress" (DEPLOYING, PROVISIONING, etc.)
2. Execute operation (Ansible/Terraform)
3. Set final status (ACTIVE/RUNNING or ERROR)
4. Commit after each status change

### Logging
- Use `append_log(instance, "message")` for user-visible logs
- Use `current_app.logger` for debug/system logs

### Helper Functions
Return `(success: bool, error_message: str or None)` for consistent error handling:
```python
def _rename_config_folder(old_name, new_name):
    # ... logic ...
    if error:
        return False, "Error message"
    return True, None
```

### Distributed Locking
Tasks acquire a lock before executing to prevent concurrent operations on the same resource:
```python
lock_token = task_lock.acquire_lock(resource_id)
try:
    # ... task logic ...
finally:
    task_lock.release_lock(resource_id, lock_token)
```

### Job Failure Handlers
Tasks are enqueued with `on_failure` callbacks to handle unexpected RQ failures (e.g., worker crash). Register failure handlers in `ui/task_logic/job_failure_handlers.py` and pass via `enqueue_task(..., on_failure=handler)`.

### ZMQ / RCON
Instance ZMQ connections (RCON + stats) are managed via `_prepare_instance_zmq()` from `ui/task_logic/zmq_utils.py`. Fields `zmq_rcon_port`, `zmq_rcon_password`, `zmq_stats_port`, `zmq_stats_password` on `QLInstance` drive connection setup.

## Instance Config Folders

Instance config directories (`configs/<host_name>/<instance_id>/`) support one level of user-managed subfolders for `.ent` files (entity overrides). This is in addition to the always-present `scripts/` and `factories/` reserved folders.

### Allowed extensions
`ALLOWED_CONFIG_EXTENSIONS` in `instance_routes.py` defines which extensions are valid inside a config folder: `.cfg`, `.txt`, `.ent`. Files with other extensions are treated as unmanaged and never deleted during sync.

### Reserved folder names
`RESERVED_CONFIG_FOLDER_NAMES = {'scripts', 'factories'}`. These may not be used as `config_folders` values and are never touched by the folder reconciliation logic.

### Backend helpers (instance_routes.py)
- `_validate_path_segment(segment, allowed_extensions)` — validates one path component (no slashes, no dotdot, no leading dot; extension check skipped when `allowed_extensions is None`).
- `_validate_relative_path(path, allowed_extensions, max_depth=2)` — splits on `/`, validates each segment, enforces depth limit and no leading/trailing slashes.
- `_validate_config_folders(folders)` — validates a list of folder names: checks reserved names, then each name via `_validate_path_segment`.
- `_validate_configs_map(configs)` — validates all keys in a `configs` dict using `_validate_relative_path`.
- `_sync_configs_to_disk(instance_dir, configs, config_folders)` — writes all files in `configs`, reconciles top-level subfolders when `config_folders` is not `None` (None = legacy/omitted = leave folders alone), and removes orphaned managed files.

### Frontend adapter
`useStateAdapter` (in `fileManager/adapters/`) tracks both file content and the `config_folders` list. `serialize()` returns `{ files: Record<path,content>, folders: string[] }`. Consumers destructure this: `const { files, folders } = serializeConfigs();`.

## Plugin Python Dependencies (`requirements.txt`)

To install Python packages required by minqlx plugins, create a `requirements.txt` file inside the instance's scripts directory:

**Location:** `configs/<host_name>/<instance_id>/scripts/requirements.txt`

**Format:** Standard pip requirements format — one package per line, e.g.:

```
requests>=2.28
redis==4.5.1
```

**Trigger:** QLSM runs `pip install -r requirements.txt` automatically on every new instance deploy, every "Apply Config", and every restart. pip skips already-satisfied packages, so this is safe to run repeatedly.

**Failure behavior:** If pip fails (e.g., a package name is wrong or the host has no internet access), QLSM logs a warning to the instance log but does not block the config sync or service restart. Review the instance log to diagnose the failure.

**Creating the file:** Use the file manager in the instance's Config tab — click "New File", name it `requirements.txt`, and enter one package per line.

## File Size Guideline
Keep source files under 300 lines of code (excluding comments/blanks). Files approaching 500 lines should be refactored into focused submodules. This guideline is aspirational — some high-complexity modules (e.g., `ansible_instance_mgmt.py`, `instance_routes.py`) currently exceed it and are candidates for future refactoring.
