"""Durable record of one minqlx -> minqlxtended host upgrade.

One row per attempt. The orchestrator owns the state machine, reservation and
recovery; the snapshot module only writes the snapshot_* columns. Imported by
ui.models so db.create_all() sees the table.
"""
import datetime
import uuid

from sqlalchemy import text
from sqlalchemy.orm import validates

from ui import db

# Nonterminal states hold the host's mutation reservation.
NONTERMINAL_STATES = (
    'preparing', 'quiescing', 'installing', 'converting', 'configuring',
    'rolling_back', 'recovery_required',
)
TERMINAL_STATES = ('succeeded', 'rolled_back', 'failed_preparation')
VALID_STATES = NONTERMINAL_STATES + TERMINAL_STATES

# The partial index names the TERMINAL states, so any nonterminal state added
# later is covered by the one-active-operation-per-host rule without a migration.
_TERMINAL_SQL = ', '.join(f"'{state}'" for state in TERMINAL_STATES)
ACTIVE_OPERATION_WHERE = f'state NOT IN ({_TERMINAL_SQL})'
ACTIVE_OPERATION_INDEX = 'uq_runtime_upgrade_active_host'


def _new_operation_id():
    return uuid.uuid4().hex


class HostRuntimeUpgradeOperation(db.Model):
    __tablename__ = 'host_runtime_upgrade_operation'
    __table_args__ = (
        db.Index(ACTIVE_OPERATION_INDEX, 'host_id', unique=True,
                 sqlite_where=text(ACTIVE_OPERATION_WHERE)),
    )

    id = db.Column(db.String(32), primary_key=True, default=_new_operation_id)
    host_id = db.Column(db.Integer, db.ForeignKey('host.id'), nullable=False, index=True)
    state = db.Column(db.String(32), nullable=False, default='preparing')
    phase = db.Column(db.String(64), nullable=True)

    # The confirmation capture. Holds ZMQ passwords: server-side only, never
    # serialized to a client.
    inputs_json = db.Column(db.Text, nullable=True)
    fingerprint = db.Column(db.String(64), nullable=True)
    answers_json = db.Column(db.Text, nullable=True)  # accepted replacements

    original_runtime = db.Column(db.String(20), nullable=True)
    original_host_status = db.Column(db.String(32), nullable=True)
    original_instance_states_json = db.Column(db.Text, nullable=True)

    snapshot_path = db.Column(db.String(500), nullable=True)
    snapshot_complete = db.Column(db.Boolean, nullable=False, default=False, server_default='0')

    instance_outcomes_json = db.Column(db.Text, nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    rq_job_id = db.Column(db.String(64), nullable=True)
    fencing_token = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    recovery_required = db.Column(db.Boolean, nullable=False, default=False, server_default='0')

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow,
                           onupdate=datetime.datetime.utcnow)

    @validates('state')
    def _validate_state(self, _key, value):
        if value not in VALID_STATES:
            raise ValueError(f'Invalid runtime upgrade state: {value!r}')
        return value

    @property
    def is_terminal(self):
        return self.state in TERMINAL_STATES

    def __repr__(self):
        return f'<HostRuntimeUpgradeOperation {self.id} host={self.host_id} {self.state}>'
