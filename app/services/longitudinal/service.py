from app.services.longitudinal.factory import get_adapter


class LongitudinalService:

    def visualizar(self, db, tipo: str, evento_id: int):

        adapter = get_adapter(tipo)

        return adapter.build_response(db, evento_id)


longitudinal_service = LongitudinalService()