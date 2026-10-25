"""Explicit synthetic evidence for isolated tests, through the real service."""
from hashlib import sha256
from datetime import timedelta
from uuid import uuid4
from app.schemas.whatsapp_autorizacao import AuthorizationCreate
from app.services.whatsapp_autorizacao import register
from app.services.whatsapp_mental import now_utc


def authorize_follow(db, scope):
    label='TEST-EVIDENCE-'+uuid4().hex
    payload=AuthorizationCreate(origem='PRESENCIAL',obtida_em=now_utc(db)-timedelta(seconds=1),
        referencia_evidencia=label,evidencia_sha256=sha256(label.encode()).hexdigest(),evidencia_verificada=True)
    result=register(db,scope,uuid4().hex,payload)
    db.commit()
    return result
