from ui.models import QLInstance


def test_qlinstance_has_ld_preload_hooks_column(app):
    columns = {column.name for column in QLInstance.__table__.columns}
    assert "ld_preload_hooks" in columns


def test_qlinstance_ld_preload_hooks_is_nullable_text(app):
    col = QLInstance.__table__.columns["ld_preload_hooks"]
    assert col.nullable is True
    assert str(col.type).upper().startswith("TEXT")
