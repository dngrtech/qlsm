import json
import io
import logging
from ui import create_app


def test_json_log_format():
    """When LOG_FORMAT=json, logs should be valid JSON with expected fields."""
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'LOG_FORMAT': 'json',
        'LOG_LEVEL': 'INFO',
        'SECRET_KEY': 'test-secret',
        'RQ_ASYNC': False,
        'RQ_CONNECTION_CLASS': 'fakeredis.FakeStrictRedis',
        'RCON_ENABLED': False,
    })

    with app.app_context():
        root_logger = logging.getLogger()
        handler = root_logger.handlers[0]
        original_stream = handler.stream
        stream = io.StringIO()
        handler.stream = stream
        try:
            app.logger.info('test message')
            output = stream.getvalue().strip()
        finally:
            handler.stream = original_stream

        log_entry = json.loads(output)
        assert log_entry['message'] == 'test message'
        assert log_entry['level'] == 'INFO'
        assert 'timestamp' in log_entry


def test_text_log_format():
    """When LOG_FORMAT=text (default), logs should be human-readable."""
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'LOG_FORMAT': 'text',
        'LOG_LEVEL': 'INFO',
        'SECRET_KEY': 'test-secret',
        'RQ_ASYNC': False,
        'RQ_CONNECTION_CLASS': 'fakeredis.FakeStrictRedis',
        'RCON_ENABLED': False,
    })

    with app.app_context():
        root_logger = logging.getLogger()
        handler = root_logger.handlers[0]
        original_stream = handler.stream
        stream = io.StringIO()
        handler.stream = stream
        try:
            app.logger.info('test message')
            output = stream.getvalue()
        finally:
            handler.stream = original_stream

        assert 'INFO' in output
        assert 'test message' in output
        try:
            json.loads(output)
            assert False, "Text format should not be valid JSON"
        except json.JSONDecodeError:
            pass


def test_info_level_suppresses_ui_debug_logs():
    """ui.* debug logs should not leak when LOG_LEVEL=INFO."""
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'LOG_FORMAT': 'json',
        'LOG_LEVEL': 'INFO',
        'SECRET_KEY': 'test-secret',
        'RQ_ASYNC': False,
        'RQ_CONNECTION_CLASS': 'fakeredis.FakeStrictRedis',
        'RCON_ENABLED': False,
    })

    with app.app_context():
        root_logger = logging.getLogger()
        handler = root_logger.handlers[0]
        original_stream = handler.stream
        stream = io.StringIO()
        handler.stream = stream
        try:
            logging.getLogger('ui.redis_listener').debug('debug should be hidden')
            logging.getLogger('ui.redis_listener').info('info should be visible')
            output_lines = [line for line in stream.getvalue().strip().splitlines() if line]
        finally:
            handler.stream = original_stream

        assert len(output_lines) == 1
        log_entry = json.loads(output_lines[0])
        assert log_entry['level'] == 'INFO'
        assert log_entry['message'] == 'info should be visible'
