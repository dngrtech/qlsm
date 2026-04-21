# Code Style & Patterns

## File size limits

- Hard limit: 300 lines of code per source file (excluding comments/blanks)
- Never exceed 500 lines — flag for refactor when approaching
- Split by functionality, not arbitrarily

## API response format

```python
# Success
{"data": {...}, "message": "optional"}

# Error
{"error": {"message": "description"}}
```

## Backend validation order

1. Type check → 2. Normalize (`.strip()`) → 3. Empty check → 4. Length check → 5. Pattern check → 6. Uniqueness check

## Route protection

All protected routes use `@jwt_required()` from `flask_jwt_extended` — parentheses required.

## Background task error handling

- Set status to ERROR on failure
- Use `append_log(instance, "message")` from `task_logic/common.py`
- Always commit status changes
- Return boolean or error string — never raise exceptions to RQ

## Documentation

After any significant change (new feature, route change, model change, new playbook, new service), update whichever of these apply:
- `docs/architecture.md`
- `docs/technical.md`
- `docs/api_reference.md`
- `docs/development_guidelines.md`
