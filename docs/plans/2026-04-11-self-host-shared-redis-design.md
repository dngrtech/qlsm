# Self-Host Shared Redis Runtime Design

## Context

`provider=self` runs the QLSM Docker stack and the Quake Live host runtime on the same machine.

Today that creates a Redis conflict:

- QLSM Docker Redis binds `127.0.0.1:6379` on the host.
- `setup_host.yml` also installs host-level `redis-server` for minqlx.
- The host service fails to start because `6379` is already occupied.
- minqlx defaults to `qlx_redisAddress=127.0.0.1`, `qlx_redisPassword=""`, and only receives `qlx_redisDatabase`.
- On self-hosts, minqlx therefore connects to QLSM Redis without auth and logs `NOAUTH Authentication required`.

## Decision

Use the existing QLSM Docker Redis for self-host game instances instead of trying to run a second Redis service on the host.

This keeps one Redis server per self-host deployment and uses logical DB separation:

- `DB 0`: QLSM app, RQ, Socket.IO, RCON service
- `DB 1`: game port `27960`
- `DB 2`: game port `27961`
- `DB 3`: game port `27962`
- `DB 4`: game port `27963`

## Runtime Contract

For `provider=self`, every game instance must receive these minqlx cvars:

- `qlx_redisAddress=127.0.0.1:6379`
- `qlx_redisPassword=<REDIS_PASSWORD>`
- `qlx_redisDatabase=<port - 27959>`

For non-self hosts, keep the current behavior. They continue to use host-local `redis-server`.

## Configuration Rules

- Self-host instance deploy/config flows must fail early if `REDIS_PASSWORD` is not configured in the QLSM environment.
- Self-host setup must not attempt to install or rely on host-level `redis-server`.
- Self-host restart validation must not require `redis-server` as a critical service.
- The Redis password will be passed in `qlds_args` for now because it is the smallest viable fix and matches the current exposure pattern of other instance secrets such as ZMQ passwords.

## Data Flow

1. User deploys or reconfigures a self-host instance.
2. Backend builds `qlds_args`.
3. Self-host branch injects Redis address, password, and DB index into those args.
4. Ansible re-renders `qlds@<port>.service`.
5. `run_server_x64_minqlx.sh` starts Quake Live with explicit minqlx Redis cvars.
6. minqlx authenticates to QLSM Redis on `127.0.0.1:6379`, but writes into `DB 1..4` instead of `DB 0`.

## Non-Goals

- Do not introduce a second Redis service for self-host deployments.
- Do not change the DB numbering formula for game instances.
- Do not redesign secret storage for service arguments in this change.
- Do not change remote standalone/Vultr Redis behavior.

## Verification

- Unit tests confirm self-host `qlds_args` includes `qlx_redisAddress`, `qlx_redisPassword`, and the correct DB index.
- Unit tests confirm non-self hosts do not get self-host Redis args.
- Unit tests confirm self-host deploy fails with a clear message when `REDIS_PASSWORD` is missing.
- Setup/restart tests confirm self-host paths no longer require host `redis-server`.
- Live smoke test confirms:
  - `qlds@27960.service` contains the Redis cvars
  - `journalctl -u qlds@27960` no longer shows `NOAUTH`
  - `redis-cli -a "$REDIS_PASSWORD" -n 1 KEYS 'minqlx:server_status:*'` returns the instance status key
