"""Explicit activation only inside owned disposable test databases."""
from sqlalchemy import text


def activate(engine):
    with engine.begin() as c:
        name = c.exec_driver_sql('SELECT current_database()').scalar_one()
        if not name.startswith(('d92a_', 'w1b_', 'e14b_legacy_', 'e14b_close_')):
            raise RuntimeError('Owned disposable database required for runtime activation')
        c.execute(text("UPDATE whatsapp_runtime SET active=true WHERE id=1"))
