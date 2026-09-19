"""Transaction-scoped identity locks shared by all Daily Record channels.

Order: responsible (when present), patient, responsible link, existing record.
PostgreSQL NO KEY UPDATE excludes competing writers/revocation but is compatible
with FK KEY SHARE. Never upgrade these identity locks to FOR UPDATE later.
No commits, retries, global locks or clinical/deduplication rules live here.
"""
from app.models.paciente import Paciente
from app.models.responsavel import Responsavel


def lock_responsible(db, responsible_id):
    # SQLAlchemy key_share=True without read=True renders FOR NO KEY UPDATE.
    return db.query(Responsavel.id).filter_by(id=responsible_id).with_for_update(key_share=True).first()


def lock_patient(db, patient_id):
    return db.query(Paciente.id).filter_by(id=patient_id).with_for_update(key_share=True).first()


def lock_context(db, patient_id, responsible_id=None):
    # No autoflush before ordering locks: caller's pending clinical state must
    # not acquire implicit FK locks ahead of the canonical identity locks.
    with db.no_autoflush:
        if responsible_id is not None:
            lock_responsible(db, responsible_id)
        lock_patient(db, patient_id)
