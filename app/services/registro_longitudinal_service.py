"""Legacy evolution facade: shares the canonical Attendance transaction."""
from app.services.session_service import SessionService


class RegistroLongitudinalService:
    @staticmethod
    def criar_a_partir_da_sessao(db, sessao, payload, *, usuario):
        return SessionService().attend(db, sessao.id, usuario, payload, legacy=True)
