import datetime
from sqlalchemy.orm.attributes import flag_modified

def append_log(model_instance, message):
    """Appends a timestamped log message to the instance's log field."""
    if not model_instance:
        return # Should not happen if called correctly

    # Use local time and include timezone name (e.g., PDT)
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')
    log_entry = f"[{timestamp}] {message}\n"

    # Append log entry, handling None case
    if model_instance.logs is None:
        model_instance.logs = log_entry
    else:
        model_instance.logs += log_entry

    # Explicitly mark the 'logs' field as modified for SQLAlchemy
    flag_modified(model_instance, "logs")

    # Note: Committing should happen in the main task function after calling this.
