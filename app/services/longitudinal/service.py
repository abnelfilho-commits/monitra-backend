"""Authorized legacy event details; contextual journeys use their own boundary."""
from fastapi import HTTPException
from sqlalchemy import select

from app.models.avaliacao_clinica import AvaliacaoClinica
from app.models.intervencao import Intervencao
from app.models.modular import RegistroLongitudinal, FormularioModulo, RespostaRegistro, CampoFormulario
from app.services.care_lines.access import authorized_patient
from app.services.care_lines.registry import NEURO
from app.services.clinical_engine.assessment_access import assessment_access
from app.services.longitudinal.factory import get_adapter


def unavailable():
    return HTTPException(404, 'Evento clínico não disponível.')


class LongitudinalService:
    def visualizar(self, db, tipo: str, evento_id: int, usuario):
        kind = tipo.upper()
        if kind in ('DENVERII', 'DENVER_II'):
            kind = 'DENVER'
        try:
            with db.no_autoflush:
                if kind in ('MCHAT', 'DENVER'):
                    # Identity only until the shared assessment ACL has passed.
                    identity = db.execute(select(AvaliacaoClinica.instrumento,
                        AvaliacaoClinica.modulo_id).where(AvaliacaoClinica.id == evento_id)).first()
                    allowed = ('DENVER', 'DENVERII', 'DENVER_II') if kind == 'DENVER' else ('MCHAT',)
                    if (identity is None or (identity.instrumento or '').upper() not in allowed
                            or identity.modulo_id != NEURO.module_id):
                        raise unavailable()
                    assessment_access(db, usuario, evento_id, denver_aliases=kind == 'DENVER')
                elif kind == 'REGISTRO':
                    row = db.execute(select(RegistroLongitudinal.paciente_id,
                        RegistroLongitudinal.modulo_id, RegistroLongitudinal.formulario_id)
                        .join(FormularioModulo, FormularioModulo.id == RegistroLongitudinal.formulario_id)
                        .where(RegistroLongitudinal.id == evento_id,
                               RegistroLongitudinal.contexto_assistencial_id.is_(None),
                               FormularioModulo.modulo_id == RegistroLongitudinal.modulo_id)).first()
                    if row is None:
                        raise unavailable()
                    authorized_patient(db, usuario, row.paciente_id, row.modulo_id)
                    # Reject mismatched/orphan answer fields without loading answers.
                    invalid = db.execute(select(RespostaRegistro.id)
                        .outerjoin(CampoFormulario, CampoFormulario.id == RespostaRegistro.campo_id)
                        .where(RespostaRegistro.registro_id == evento_id,
                               (CampoFormulario.id.is_(None)) |
                               (CampoFormulario.formulario_id != row.formulario_id)).limit(1)).first()
                    if invalid is not None:
                        raise unavailable()
                elif kind == 'INTERVENCAO':
                    row = db.execute(select(Intervencao.paciente_id, Intervencao.modulo_id)
                        .where(Intervencao.id == evento_id, Intervencao.contexto_assistencial_id.is_(None))).first()
                    if row is None:
                        raise unavailable()
                    authorized_patient(db, usuario, row.paciente_id, row.modulo_id)
                else:
                    raise unavailable()
                return get_adapter(kind).build_response(db, evento_id)
        except HTTPException as exc:
            if exc.status_code in (400, 403, 404):
                raise unavailable() from None
            raise
        except Exception:
            raise HTTPException(500, 'Não foi possível consultar o evento clínico.') from None


longitudinal_service = LongitudinalService()
