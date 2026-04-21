---
paths:
  - "frontend-react/**/*"
---

# Frontend Rules

## React state for real-time updates

Parent components manage item IDs, not full objects. Re-derive objects from the master data list on each render — this ensures child components receive fresh data after polling updates.

## CSS/UI fixes

- Verify the change visually makes sense before committing
- Never regress from a previously working state
- If a fix doesn't work on first attempt, stop and re-examine — don't iterate blindly
