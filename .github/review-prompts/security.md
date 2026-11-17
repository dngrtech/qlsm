## Lens: security

Find vulnerabilities an attacker could actually reach in this deployment.
`docs/security/threat_model.md` has the full threat model. In short:
- The panel has one trusted admin. Assume an attacker is unauthenticated on the
  network, a player on a managed game server, or someone who controls a value
  stored on a remote host (server names, map names, plugin files, player names
  arriving over RCON and stats).
- Remote QLDS hosts are less trusted than the panel. Data read back from them is
  input.

What to report. Trace each one from source to sink:
- Command injection: user- or host-controlled strings reaching `subprocess`, shell
  strings, Ansible `--extra-vars`, Terraform vars, `ssh` command lines, or RCON
  commands that feed console-command injection.
- Path traversal: identifiers reaching filesystem paths under `configs/`,
  plugin directories, uploads and backups.
- Missing `@jwt_required()` on a new or changed route, or a route that changes
  state without the CSRF protection the rest of the app uses.
- Secrets: credentials, SSH keys or tokens committed, logged, returned in an API
  response, or written to world-readable files.
- XSS: `dangerouslySetInnerHTML`, or rendering host- or player-controlled strings
  as HTML or Markdown without sanitising them.
- SSRF: user-controlled URLs fetched server-side (plugin repositories, update
  checks).
- Unsafe deserialisation (pickle, yaml.load) of untrusted data.
- New or changed dependencies, and GitHub Actions changes (`pull_request_target`,
  unpinned third-party actions, secrets exposed to forked PRs).

Not in this lens. These are not findings here:
- Theoretical issues with no reachable source → sink path in this code.
- Missing MFA, rate limiting or account lockout on the single-admin login, unless
  the PR changes the auth flow.
- "Consider using library X" or general hardening advice.
- Generic OWASP items that the PR doesn't touch.
