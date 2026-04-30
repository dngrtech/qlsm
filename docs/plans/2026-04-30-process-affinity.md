# Process Affinity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically hard-pin QLDS instances to host CPUs when a host has more than one CPU, and show the assigned CPU in the instance details drawer.

**Architecture:** Store nullable `Host.cpu_count` and `QLInstance.cpu_affinity` fields. Add a small CPU affinity helper that resolves host CPU count, chooses the least-used valid CPU, persists the assignment, and passes it to Ansible service-rendering flows. Render systemd `CPUAffinity=` only when an instance has an assigned CPU; existing instances remain unset until a natural service re-render or manual DB assignment plus restart.

**Tech Stack:** Flask, SQLAlchemy, Alembic/Flask-Migrate, RQ task logic, Ansible systemd templates, React, Vitest, Pytest.

---

### Task 1: Add Schema And API Fields

**Files:**
- Modify: `ui/models.py`
- Create: `migrations/versions/20260430000000_add_cpu_affinity_fields.py`
- Modify: `tests/test_db.py`

**Step 1: Write failing model/API tests**

Add tests near the existing instance and host database tests in `tests/test_db.py`:

```python
def test_host_to_dict_includes_cpu_count(app_context):
    host = create_host(
        name='cpu-host',
        provider='vultr',
        region='ewr',
        machine_size='vhf-2c-2gb',
        status=HostStatus.ACTIVE,
        cpu_count=2,
    )

    assert host.to_dict()['cpu_count'] == 2


def test_instance_to_dict_includes_cpu_affinity(app_context):
    host = create_host(
        name='cpu-instance-host',
        provider='vultr',
        region='ewr',
        machine_size='vhf-2c-2gb',
        status=HostStatus.ACTIVE,
    )
    instance = create_instance(
        name='CPU Affinity Instance',
        host_id=host.id,
        port=27960,
        hostname='CPU Affinity Server',
    )
    update_instance(instance.id, cpu_affinity=1)

    assert get_instance(instance.id).to_dict()['cpu_affinity'] == 1
```

**Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_db.py::test_host_to_dict_includes_cpu_count tests/test_db.py::test_instance_to_dict_includes_cpu_affinity -v
```

Expected: FAIL because `cpu_count` and `cpu_affinity` are not model fields yet.

**Step 3: Add model fields**

In `ui/models.py`, add:

```python
cpu_count = db.Column(db.Integer, nullable=True)
```

to `Host`, and include `'cpu_count': self.cpu_count` in `Host.to_dict()`.

Add:

```python
cpu_affinity = db.Column(db.Integer, nullable=True)
```

to `QLInstance`, and include `'cpu_affinity': self.cpu_affinity` in `QLInstance.to_dict()`.

**Step 4: Add migration**

Create `migrations/versions/20260430000000_add_cpu_affinity_fields.py`:

```python
"""add cpu affinity fields

Revision ID: 20260430000000
Revises: c940478a96df
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa

revision = '20260430000000'
down_revision = 'c940478a96df'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('host', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cpu_count', sa.Integer(), nullable=True))
    with op.batch_alter_table('ql_instance', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cpu_affinity', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('ql_instance', schema=None) as batch_op:
        batch_op.drop_column('cpu_affinity')
    with op.batch_alter_table('host', schema=None) as batch_op:
        batch_op.drop_column('cpu_count')
```

**Step 5: Run tests to verify pass**

Run:

```bash
pytest tests/test_db.py::test_host_to_dict_includes_cpu_count tests/test_db.py::test_instance_to_dict_includes_cpu_affinity -v
```

Expected: PASS.

**Step 6: Commit**

```bash
git add ui/models.py migrations/versions/20260430000000_add_cpu_affinity_fields.py tests/test_db.py
git commit -m "feat: add cpu affinity fields"
```

---

### Task 2: Add CPU Affinity Assignment Helper

**Files:**
- Create: `ui/task_logic/cpu_affinity.py`
- Create: `tests/test_cpu_affinity.py`

**Step 1: Write failing tests**

Create `tests/test_cpu_affinity.py` with focused unit tests:

```python
from ui import db
from ui.database import create_host, create_instance
from ui.models import HostStatus
from ui.task_logic.cpu_affinity import (
    choose_least_used_cpu,
    ensure_instance_cpu_affinity,
    resolve_host_cpu_count,
)


def test_resolve_vultr_cpu_count_from_plan(app_context):
    host = create_host(
        name='vultr-cpu-host',
        provider='vultr',
        region='ewr',
        machine_size='vhf-2c-2gb',
        status=HostStatus.ACTIVE,
    )

    assert resolve_host_cpu_count(host) == 2
    assert host.cpu_count == 2


def test_one_cpu_host_leaves_affinity_unset(app_context):
    host = create_host(
        name='one-cpu-host',
        provider='vultr',
        region='ewr',
        machine_size='vhf-1c-1gb',
        status=HostStatus.ACTIVE,
    )
    inst = create_instance('one-cpu-inst', host.id, 27960, 'One CPU')

    assert ensure_instance_cpu_affinity(inst) is None
    assert inst.cpu_affinity is None


def test_skipped_ports_still_spread_by_existing_instances(app_context):
    host = create_host(
        name='skip-port-host',
        provider='vultr',
        region='ewr',
        machine_size='vhf-2c-2gb',
        status=HostStatus.ACTIVE,
    )
    first = create_instance('inst-27960', host.id, 27960, 'First')
    second = create_instance('inst-27962', host.id, 27962, 'Second')

    assert ensure_instance_cpu_affinity(first) == 0
    db.session.commit()
    assert ensure_instance_cpu_affinity(second) == 1


def test_existing_valid_affinity_is_stable(app_context):
    host = create_host(
        name='stable-affinity-host',
        provider='vultr',
        region='ewr',
        machine_size='vhf-2c-2gb',
        status=HostStatus.ACTIVE,
    )
    inst = create_instance('stable-inst', host.id, 27960, 'Stable')
    inst.cpu_affinity = 1
    db.session.commit()

    assert ensure_instance_cpu_affinity(inst) == 1
    assert inst.cpu_affinity == 1


def test_out_of_range_affinity_is_repaired(app_context):
    host = create_host(
        name='repair-affinity-host',
        provider='vultr',
        region='ewr',
        machine_size='vhf-2c-2gb',
        status=HostStatus.ACTIVE,
    )
    inst = create_instance('repair-inst', host.id, 27960, 'Repair')
    inst.cpu_affinity = 9
    db.session.commit()

    assert ensure_instance_cpu_affinity(inst) == 0
    assert inst.cpu_affinity == 0
```

Add a subprocess-mocked test later if remote `nproc` detection is implemented in this helper.

**Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_cpu_affinity.py -v
```

Expected: FAIL because `ui.task_logic.cpu_affinity` does not exist.

**Step 3: Implement helper**

Create `ui/task_logic/cpu_affinity.py`:

```python
import logging
import os
import subprocess

from ui import db
from ui.vultr_plans import get_plan

log = logging.getLogger(__name__)


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _infer_vultr_cpu_count(host):
    if getattr(host, 'provider', None) != 'vultr':
        return None
    plan = get_plan(getattr(host, 'machine_size', None))
    if not plan:
        return None
    return _positive_int(plan.get('vcpu'))


def _detect_cpu_count_with_ansible(host):
    inventory_path = os.path.abspath('ansible/inventory/')
    cmd = [
        'ansible',
        '-i',
        inventory_path,
        host.name,
        '-m',
        'command',
        '-a',
        'nproc',
    ]
    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
            env=os.environ,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("Could not detect CPU count for host %s: %s", host.name, exc)
        return None
    if result.returncode != 0:
        log.warning("CPU count detection failed for host %s: %s", host.name, result.stderr.strip())
        return None
    for token in reversed(result.stdout.split()):
        parsed = _positive_int(token)
        if parsed:
            return parsed
    return None


def resolve_host_cpu_count(host):
    saved = _positive_int(getattr(host, 'cpu_count', None))
    if saved:
        return saved

    detected = _infer_vultr_cpu_count(host)
    if detected is None:
        detected = _detect_cpu_count_with_ansible(host)

    if detected:
        host.cpu_count = detected
    return detected


def choose_least_used_cpu(host, cpu_count, exclude_instance_id=None):
    counts = [0 for _ in range(cpu_count)]
    for inst in getattr(host, 'instances', []) or []:
        if exclude_instance_id is not None and inst.id == exclude_instance_id:
            continue
        affinity = _positive_int(getattr(inst, 'cpu_affinity', None))
        if affinity is not None and 0 <= affinity < cpu_count:
            counts[affinity] += 1
    return min(range(cpu_count), key=lambda cpu: (counts[cpu], cpu))


def ensure_instance_cpu_affinity(instance):
    host = getattr(instance, 'host', None)
    if not host:
        return None
    cpu_count = resolve_host_cpu_count(host)
    if not cpu_count or cpu_count <= 1:
        instance.cpu_affinity = None
        return None

    existing = _positive_int(getattr(instance, 'cpu_affinity', None))
    if existing is not None and 0 <= existing < cpu_count:
        return existing

    assigned = choose_least_used_cpu(host, cpu_count, exclude_instance_id=instance.id)
    instance.cpu_affinity = assigned
    return assigned
```

Only commit this helper after tests pass. If any test shows SQLAlchemy relationship staleness, refresh `host` before `ensure_instance_cpu_affinity(second)` in the test rather than adding broad session churn to production code.

**Step 4: Run tests**

Run:

```bash
pytest tests/test_cpu_affinity.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add ui/task_logic/cpu_affinity.py tests/test_cpu_affinity.py
git commit -m "feat: assign instance cpu affinity"
```

---

### Task 3: Pass CPU Affinity Through Instance Task Logic

**Files:**
- Modify: `ui/task_logic/ansible_instance_mgmt.py`
- Modify: `tests/test_task_deploy_instance.py`
- Modify: `tests/test_task_restart_instance.py`
- Modify: `tests/test_task_apply_config.py`
- Modify: `tests/test_task_self_host_instance_network.py`

**Step 1: Write failing integration tests**

In each task test file, patch the helper and assert the Ansible extravars include `cpu_affinity`.

Example for `tests/test_task_deploy_instance.py`:

```python
@patch(f'{TASK_LOGIC_MODULE}.ensure_instance_cpu_affinity', return_value=1)
@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook')
@patch(f'{TASK_LOGIC_MODULE}._build_qlds_args_string', return_value='mock_qlds_args')
@patch(f'{TASK_LOGIC_MODULE}._prepare_instance_zmq')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_deploy_instance_passes_cpu_affinity(
    mock_get_job, mock_session, mock_append_log, mock_prep_zmq,
    mock_build_args, mock_run_playbook, mock_ensure_affinity, test_app
):
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job
    mock_instance = _make_mock_instance()
    mock_session.get.return_value = mock_instance
    mock_run_playbook.return_value = (SimpleAnsibleResult(0, 'ok', ''), None)

    deploy_instance(10)

    extravars = mock_run_playbook.call_args.kwargs['extravars']
    assert extravars['cpu_affinity'] == 1
```

Repeat the same pattern for restart and config apply. For LAN rate, add or extend a test in `tests/test_task_self_host_instance_network.py` around `reconfigure_instance_lan_rate`.

**Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_task_deploy_instance.py::test_deploy_instance_passes_cpu_affinity tests/test_task_restart_instance.py::test_restart_instance_passes_cpu_affinity tests/test_task_apply_config.py::test_apply_instance_config_passes_cpu_affinity -v
```

Expected: FAIL because `ensure_instance_cpu_affinity` is not imported/called.

**Step 3: Implement task wiring**

In `ui/task_logic/ansible_instance_mgmt.py`, import:

```python
from .cpu_affinity import ensure_instance_cpu_affinity
```

In `deploy_instance_logic`, `restart_instance_logic`, `apply_instance_config_logic`, and `reconfigure_instance_lan_rate_logic`, call:

```python
cpu_affinity = ensure_instance_cpu_affinity(instance)
```

after `_prepare_instance_zmq(instance)` and before creating the extravars dict.

Add to each render/restart extravars dict:

```python
'cpu_affinity': cpu_affinity,
```

Commit only after all targeted task tests pass.

**Step 4: Run tests**

Run:

```bash
pytest tests/test_task_deploy_instance.py tests/test_task_restart_instance.py tests/test_task_apply_config.py tests/test_task_self_host_instance_network.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add ui/task_logic/ansible_instance_mgmt.py tests/test_task_deploy_instance.py tests/test_task_restart_instance.py tests/test_task_apply_config.py tests/test_task_self_host_instance_network.py
git commit -m "feat: pass cpu affinity to qlds service tasks"
```

---

### Task 4: Render Systemd CPUAffinity

**Files:**
- Modify: `ansible/templates/qlds@.service.j2`
- Create: `tests/test_qlds_service_template.py`

**Step 1: Write failing template tests**

Create `tests/test_qlds_service_template.py`:

```python
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def _render_service(**kwargs):
    template_dir = Path('ansible/templates').resolve()
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template('qlds@.service.j2')
    return template.render(**kwargs)


def test_qlds_service_omits_cpu_affinity_when_unset():
    rendered = _render_service(qlds_args='+set net_port 27960')

    assert 'CPUAffinity=' not in rendered


def test_qlds_service_renders_cpu_affinity_when_set():
    rendered = _render_service(qlds_args='+set net_port 27960', cpu_affinity=1)

    assert 'CPUAffinity=1' in rendered
```

**Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_qlds_service_template.py -v
```

Expected: second test FAILS because the template does not render `CPUAffinity`.

**Step 3: Update template**

In `ansible/templates/qlds@.service.j2`, add under `WorkingDirectory` and before `ExecStart`:

```jinja2
{% if cpu_affinity is defined and cpu_affinity is not none %}
CPUAffinity={{ cpu_affinity }}
{% endif %}
```

Do not change `ExecStart`.

**Step 4: Run tests**

Run:

```bash
pytest tests/test_qlds_service_template.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add ansible/templates/qlds@.service.j2 tests/test_qlds_service_template.py
git commit -m "feat: render qlds cpu affinity"
```

---

### Task 5: Show CPU Affinity In Instance Details Drawer

**Files:**
- Modify: `frontend-react/src/components/instances/InstanceDetailsModal.jsx`
- Modify: `frontend-react/src/components/instances/__tests__/InstanceDetailsModal.test.jsx`

**Step 1: Write failing frontend tests**

In `InstanceDetailsModal.test.jsx`, add a new describe block or append tests:

```jsx
it('shows assigned CPU affinity in details', async () => {
  mocks.getInstanceById.mockResolvedValue({
    id: 6,
    name: 'inst-6',
    host_id: 10,
    host_name: 'cpu-host',
    host_os_type: 'debian',
    host_ip_address: '203.0.113.12',
    port: 27960,
    hostname: 'CPU Server',
    lan_rate_enabled: false,
    status: 'RUNNING',
    cpu_affinity: 1,
  });

  render(<InstanceDetailsModal isOpen={true} instanceId={6} onClose={vi.fn()} onInstanceDeleted={vi.fn()} onInstanceUpdated={vi.fn()} onOpenEditConfig={vi.fn()} onOpenHostDrawer={vi.fn()} serverStatus={null} />);

  expect(await screen.findByText('CPU Affinity')).toBeInTheDocument();
  expect(screen.getByText('CPU 1')).toBeInTheDocument();
});


it('shows automatic CPU affinity when unset', async () => {
  mocks.getInstanceById.mockResolvedValue({
    id: 7,
    name: 'inst-7',
    host_id: 10,
    host_name: 'one-cpu-host',
    host_os_type: 'debian',
    host_ip_address: '203.0.113.13',
    port: 27961,
    hostname: 'Automatic Server',
    lan_rate_enabled: false,
    status: 'RUNNING',
    cpu_affinity: null,
  });

  render(<InstanceDetailsModal isOpen={true} instanceId={7} onClose={vi.fn()} onInstanceDeleted={vi.fn()} onInstanceUpdated={vi.fn()} onOpenEditConfig={vi.fn()} onOpenHostDrawer={vi.fn()} serverStatus={null} />);

  expect(await screen.findByText('CPU Affinity')).toBeInTheDocument();
  expect(screen.getByText('Automatic')).toBeInTheDocument();
});
```

If the one-line render becomes too long for lint readability, create a local `renderDrawer(instanceId)` helper in the test file.

**Step 2: Run tests to verify failure**

Run:

```bash
cd frontend-react && pnpm exec vitest run src/components/instances/__tests__/InstanceDetailsModal.test.jsx
```

Expected: FAIL because the field is not rendered.

**Step 3: Update drawer UI**

In `InstanceDetailsModal.jsx`, add a display value before the return:

```jsx
const cpuAffinityLabel = Number.isInteger(instance?.cpu_affinity)
  ? `CPU ${instance.cpu_affinity}`
  : 'Automatic';
```

In the `Details` section, near `Port` and before `Hostname`, add:

```jsx
<Field label="CPU Affinity"><span className="font-mono">{cpuAffinityLabel}</span></Field>
```

Do not add this field to rows, forms, live status, or the host drawer.

**Step 4: Run tests**

Run:

```bash
cd frontend-react && pnpm exec vitest run src/components/instances/__tests__/InstanceDetailsModal.test.jsx
```

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend-react/src/components/instances/InstanceDetailsModal.jsx frontend-react/src/components/instances/__tests__/InstanceDetailsModal.test.jsx
git commit -m "feat: show instance cpu affinity"
```

---

### Task 6: Document Runtime Behavior

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/technical.md`

**Step 1: Update architecture docs**

In `docs/architecture.md`, update the SQLite model descriptions:

```markdown
* **Host Model:** Stores information about target servers... `cpu_count` records the detected or inferred Linux CPU count used for transparent QLDS affinity assignment.
* **QLInstance Model:** Stores information about Quake Live server instances... `cpu_affinity` records the optional Linux CPU index assigned to the systemd service when the host has more than one CPU.
```

**Step 2: Update technical docs**

In `docs/technical.md`, add a short subsection near the Ansible/systemd description:

```markdown
### QLDS CPU Affinity

When a host has more than one CPU, QLSM assigns each QLDS instance a persisted Linux CPU index using a least-used strategy. Service files render systemd `CPUAffinity=<cpu>` only when an assignment exists. One CPU hosts and hosts with unknown CPU counts omit affinity and use normal Linux scheduling. Existing instances are not restarted or rewritten during upgrade; they get affinity on the next QLSM-managed service render, or after manual DB assignment plus an instance restart.
```

**Step 3: Commit**

```bash
git add docs/architecture.md docs/technical.md
git commit -m "docs: describe qlds cpu affinity"
```

---

### Task 7: Final Verification And Review

**Files:**
- No code changes unless verification finds a bug.

**Step 1: Run backend targeted tests**

Run:

```bash
pytest tests/test_cpu_affinity.py tests/test_qlds_service_template.py tests/test_db.py tests/test_task_deploy_instance.py tests/test_task_restart_instance.py tests/test_task_apply_config.py tests/test_task_self_host_instance_network.py -v
```

Expected: PASS.

**Step 2: Run frontend targeted tests**

Run:

```bash
cd frontend-react && pnpm exec vitest run src/components/instances/__tests__/InstanceDetailsModal.test.jsx
```

Expected: PASS.

**Step 3: Run frontend lint**

Run:

```bash
cd frontend-react && pnpm lint
```

Expected: PASS or only pre-existing lint failures unrelated to this change.

**Step 4: Inspect git state**

Run:

```bash
git status --short
git log --oneline -8
```

Expected: clean tree and a sequence of focused commits for the feature.

**Step 5: Request code review**

Use @requesting-code-review before publishing or merging. Ask the reviewer to focus on upgrade safety, service render behavior, and the least-used CPU assignment edge cases.

**Step 6: Publish PR**

Use the GitHub publish workflow after review fixes are complete. Open a draft PR and stop for explicit merge approval.
