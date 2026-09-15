"""Compatibility entry points over the institutional Session boundary."""
from app.services.session_service import SessionService


class AssistentialExecutionService:
    @staticmethod
    def confirmar(db, sessao, *, usuario):
        return SessionService().transition(db, sessao.id, usuario, 'confirmar')

    @staticmethod
    def iniciar(db, sessao, *, usuario):
        return SessionService().transition(db, sessao.id, usuario, 'iniciar')

    @staticmethod
    def finalizar(db, sessao, *, usuario):
        return SessionService().transition(db, sessao.id, usuario, 'finalizar')

    @staticmethod
    def reagendar(db, sessao, motivo=None, *, usuario):
        return SessionService().transition(db, sessao.id, usuario, 'reagendar', motivo)

    @staticmethod
    def registrar_atendimento(db, sessao, payload, *, usuario):
        return SessionService().attend(db, sessao.id, usuario, payload)
