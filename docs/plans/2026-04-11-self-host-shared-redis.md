# Self-Host Shared Redis Runtime Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `provider=self` game instances reuse the QLSM Docker Redis with explicit minqlx auth and DB selection, while removing the conflicting host-level Redis requirement from the self-host setup and restart paths.

**Architecture:** Keep QLSM services on Redis `DB 0` and keep the existing minqlx DB formula `port - 27959` for game instances. Inject `qlx_redisAddress`, `qlx_redisPassword`, and `qlx_redisDatabase` only for self-host instances, fail early when the shared Redis password is unavailable, and stop treating host `redis-server` as part of the self-host runtime contract.

**Tech Stack:** Flask, RQ, SQLAlchemy, Ansible, systemd, Redis, Pytest

---

### Task 1: Add Explicit Self-Host Redis Args to `qlds_args`

**Files:**
- Modify: `ui/task_logic/ansible_instance_mgmt.py`
- Test: `tests/test_task_deploy_instance.py`

**Step 1: Write the failing tests**

Add focused `_build_qlds_args_string()` coverage to `tests/test_task_deploy_instance.py`:

```python
def test_build_qlds_args_self_host_includes_shared_redis_runtime(test_app, monkeypatch):
    with test_app.app_context():
        monkeypatch.setenv("REDIS_PASSWORD", "shared-secret")
        inst = _make_instance_for_args()
        inst.host = SimpleNamespace(provider="self")
        result = _build_qlds_args_string(inst)
        assert '+set qlx_redisAddress "127.0.0.1:6379"' in result
        assert '+set qlx_redisPassword "shared-secret"' in result
        assert '+set qlx_redisDatabase 1' in result


def test_build_qlds_args_non_self_host_does_not_include_shared_redis_runtime(test_app, monkeypatch):
    with test_app.app_context():
        monkeypatch.setenv("REDIS_PASSWORD", "shared-secret")
        inst = _make_instance_for_args()
        inst.host = SimpleNamespace(provider="standalone")
        result = _build_qlds_args_string(inst)
        assert "qlx_redisAddress" not in result
        assert "qlx_redisPassword" not in result


def test_build_qlds_args_self_host_requires_redis_password(test_app, monkeypatch):
    with test_app.app_context():
        monkeypatch.delenv("REDIS_PASSWORD", raising=False)
        inst = _make_instance_for_args()
        inst.host = SimpleNamespace(provider="self")
        with pytest.raises(ValueError, match="Self-host instance Redis password is not configured."):
            _build_qlds_args_string(inst)
```

Update `_make_instance_for_args()` so `inst.host` exists by default:

```python
inst.host = kwargs.get("host", SimpleNamespace(provider="standalone"))
```

**Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_task_deploy_instance.py -k redis -v`

Expected: FAIL because `_build_qlds_args_string()` currently only adds `qlx_redisDatabase`.

**Step 3: Write the minimal implementation**

In `ui/task_logic/ansible_instance_mgmt.py`, add a small helper near `_build_qlds_args_string()`:

```python
from .self_host_network import is_self_host


def _self_host_redis_args(instance):
    if not is_self_host(getattr(instance, "host", None)):
        return []

    redis_password = (os.environ.get("REDIS_PASSWORD") or "").strip()
    if not redis_password:
        raise ValueError("Self-host instance Redis password is not configured.")

    return [
        '+set qlx_redisAddress "127.0.0.1:6379"',
        f'+set qlx_redisPassword "{redis_password}"',
    ]
```

Then merge it into `_build_qlds_args_string()`:

```python
parts += [
    '+set net_strict 1',
    f'+set net_port {instance.port}',
    f'+set sv_hostname "{instance.hostname}"',
    f'+set qlx_serverBrandName "{instance.hostname}"',
]
parts += _self_host_redis_args(instance)
parts += [
    f'+set qlx_redisDatabase {redis_db_index}',
    f'+set fs_homepath {homepath}',
    f'+set qlx_pluginsPath {homepath}/minqlx-plugins',
    ...
]
```

**Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_task_deploy_instance.py -k redis -v`

Expected: PASS

**Step 5: Commit**

```bash
git add ui/task_logic/ansible_instance_mgmt.py tests/test_task_deploy_instance.py
git commit -m "fix: add shared redis args for self-host instances"
```

### Task 2: Lock In Self-Host Failure Behavior and Lifecycle Coverage

**Files:**
- Modify: `tests/test_task_deploy_instance.py`
- Modify: `tests/test_task_self_host_instance_network.py`

**Step 1: Write the failing tests**

Add a deploy-path failure test to `tests/test_task_deploy_instance.py`:

```python
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_deploy_instance_self_host_missing_redis_password_sets_error(
    mock_get_job, mock_session, mock_append_log, test_app, monkeypatch
):
    mock_job = MagicMock()
    mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)

    mock_instance = _make_mock_instance()
    mock_instance.host.provider = 'self'
    mock_session.get.return_value = mock_instance

    result = deploy_instance(mock_instance.id)

    assert mock_instance.status == InstanceStatus.ERROR
    assert "Self-host instance Redis password is not configured." in result
```

Extend `tests/test_task_self_host_instance_network.py` with one helper assertion:

```python
def _assert_self_host_redis_qlds_args(mock_run):
    qlds_args = mock_run.call_args.kwargs['extravars']['qlds_args']
    assert '+set qlx_redisAddress "127.0.0.1:6379"' in qlds_args
    assert '+set qlx_redisPassword "shared-secret"' in qlds_args
```

Then use it in the deploy/apply/reconfigure tests with `monkeypatch.setenv("REDIS_PASSWORD", "shared-secret")`.

**Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_task_deploy_instance.py::test_deploy_instance_self_host_missing_redis_password_sets_error -v`

Expected: FAIL because the deploy path does not yet surface the explicit self-host Redis message.

Run: `pytest tests/test_task_self_host_instance_network.py -v`

Expected: FAIL because the rendered `qlds_args` still lacks self-host Redis cvars.

**Step 3: Make the behavior explicit**

No new architecture is needed beyond Task 1. Keep the implementation minimal:

- Let `_build_qlds_args_string()` raise `ValueError` for missing `REDIS_PASSWORD`
- Rely on the existing task-level `except Exception as e` blocks in:
  - `deploy_instance_logic()`
  - `restart_instance_logic()`
  - `apply_instance_config_logic()`
  - `reconfigure_instance_lan_rate_logic()`

Those handlers already set `InstanceStatus.ERROR`, append a task log, and return the error string.

**Step 4: Run the verification suite**

Run: `pytest tests/test_task_deploy_instance.py tests/test_task_self_host_instance_network.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_task_deploy_instance.py tests/test_task_self_host_instance_network.py
git commit -m "test: cover self-host shared redis lifecycle behavior"
```

### Task 3: Stop Requiring Host `redis-server` for Self-Host Setup and Restart

**Files:**
- Modify: `ui/task_logic/standalone_host_setup.py`
- Modify: `ansible/playbooks/setup_host.yml`
- Modify: `ui/task_logic/ansible_host_restart.py`
- Create: `tests/test_task_ansible_host_restart.py`
- Modify: `tests/test_standalone_host_setup.py`

**Step 1: Write the failing tests**

In `tests/test_standalone_host_setup.py`, add a small helper-level test:

```python
def test_setup_playbook_vars_disable_host_redis_for_self_host():
    from ui.task_logic.standalone_host_setup import _setup_playbook_extra_vars
    host = SimpleNamespace(provider='self', ssh_port=22, timezone='UTC')
    assert _setup_playbook_extra_vars(host)['use_host_redis'] == 'false'


def test_setup_playbook_vars_keep_host_redis_for_standalone_host():
    from ui.task_logic.standalone_host_setup import _setup_playbook_extra_vars
    host = SimpleNamespace(provider='standalone', ssh_port=22, timezone='UTC')
    assert _setup_playbook_extra_vars(host).get('use_host_redis', 'true') == 'true'
```

Create `tests/test_task_ansible_host_restart.py` with:

```python
from unittest.mock import patch

from ui.database import create_host
from ui.task_logic.ansible_host_restart import restart_host_ansible_logic
from ui.models import HostStatus


@patch('ui.task_logic.ansible_host_restart._run_host_ansible_playbook', return_value=(True, 'ok', ''))
def test_restart_self_host_does_not_require_redis_server(mock_run, app):
    with app.app_context():
        host = create_host(
            name='self-restart-host',
            provider='self',
            status=HostStatus.ACTIVE,
            is_standalone=True,
        )

        assert restart_host_ansible_logic(host.id) is True
        assert mock_run.call_args.kwargs['extravars']['critical_services'] == ['ssh']
```

**Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_standalone_host_setup.py tests/test_task_ansible_host_restart.py -v`

Expected: FAIL because no setup helper exists yet and restart logic does not override `critical_services`.

**Step 3: Implement the minimal code and playbook changes**

In `ui/task_logic/standalone_host_setup.py`, extract setup vars:

```python
def _setup_playbook_extra_vars(host):
    extra_vars = {
        'is_standalone': 'true',
        'ssh_port': str(host.ssh_port),
        'firewall_mode': 'helper' if host.provider == 'self' else 'full',
    }
    if host.provider == 'self':
        extra_vars['use_host_redis'] = 'false'
    if host.timezone:
        extra_vars['host_timezone'] = host.timezone
    return extra_vars
```

Use it in `_run_setup_playbook()` instead of hardcoding the `-e` list.

In `ansible/playbooks/setup_host.yml`, make `redis-server` conditional:

```yaml
    use_host_redis: true

    - name: Install prereqs
      apt:
        pkg: "{{ base_packages
                 + ((use_host_redis | bool) | ternary(['redis-server'], []))
                 + ((firewall_mode == 'full') | ternary(['iptables-persistent'], [])) }}"
      vars:
        base_packages:
          - rsync
          - apt-transport-https
          - ca-certificates
          - curl
          - git
          - net-tools
          - wget
          - build-essential
          - lib32gcc-s1
          - lib32stdc++6
          - libc6-i386
          - python3
          - python3-dev
          - python3-pip
          - python3.11
          - python3.11-dev
          - iptables
          - sudo
```

In `ui/task_logic/ansible_host_restart.py`, pass self-host-specific critical services:

```python
extra_vars = {}
if host.provider == 'self':
    extra_vars['critical_services'] = ['ssh']
```

**Step 4: Run verification**

Run: `pytest tests/test_standalone_host_setup.py tests/test_task_ansible_host_restart.py -v`

Expected: PASS

Run: `ANSIBLE_LOCAL_TEMP=/tmp/ansible-local ansible-playbook --syntax-check -i localhost, ansible/playbooks/setup_host.yml`

Expected: PASS

Run: `ANSIBLE_LOCAL_TEMP=/tmp/ansible-local ansible-playbook --syntax-check -i localhost, ansible/playbooks/restart_host.yml`

Expected: PASS

**Step 5: Commit**

```bash
git add ui/task_logic/standalone_host_setup.py ui/task_logic/ansible_host_restart.py ansible/playbooks/setup_host.yml tests/test_standalone_host_setup.py tests/test_task_ansible_host_restart.py
git commit -m "fix: remove host redis requirement from self-host runtime"
```

### Task 4: Document the Shared Redis Contract and Run Full Verification

**Files:**
- Modify: `docs/technical.md`
- Modify: `docs/architecture.md`

**Step 1: Write the documentation updates**

In `docs/technical.md`, add a short self-host runtime note:

```markdown
For `provider=self`, game instances reuse the QLSM Docker Redis on `127.0.0.1:6379`.
QLSM reserves Redis `DB 0`; minqlx instances use `DB 1..4` derived from `port - 27959`.
Self-host minqlx services receive `qlx_redisAddress`, `qlx_redisPassword`, and `qlx_redisDatabase` explicitly at deploy time.
```

In `docs/architecture.md`, update the self-host flow section to mention that host-level `redis-server` is not part of the self-host runtime and that minqlx writes live status into the shared Redis with per-instance DB separation.

**Step 2: Run the regression suite**

Run: `pytest tests/test_task_deploy_instance.py tests/test_task_self_host_instance_network.py tests/test_standalone_host_setup.py tests/test_task_ansible_host_restart.py -v`

Expected: PASS

**Step 3: Run live smoke checks on the self-host**

Run:

```bash
ssh root@173.199.93.224 "systemctl cat qlds@27960 | sed -n '1,80p'"
```

Expected: `ExecStart` contains `qlx_redisAddress`, `qlx_redisPassword`, and `qlx_redisDatabase 1`.

Run:

```bash
ssh root@173.199.93.224 "journalctl -u qlds@27960 -n 80 --no-pager | grep NOAUTH || true"
```

Expected: no `NOAUTH Authentication required` lines after redeploy/restart.

Run:

```bash
ssh root@173.199.93.224 "cd /root/qlsm && . .env && redis-cli --no-auth-warning -a \"$REDIS_PASSWORD\" -n 1 KEYS 'minqlx:server_status:*'"
```

Expected: returns `minqlx:server_status:27960` once the instance is running.

**Step 4: Commit**

```bash
git add docs/technical.md docs/architecture.md
git commit -m "docs: describe self-host shared redis runtime"
```
