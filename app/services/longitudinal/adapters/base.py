from abc import ABC, abstractmethod


class LongitudinalAdapter(ABC):

    def response(
        self,
        *,
        tipo,
        titulo,
        subtitulo="",
        data=None,
        profissional=None,
        origem=None,
        cards=None,
        conteudo=None,
        interpretacao=None,
        conduta=None,
    ):
        return {
            "tipo": tipo,
            "titulo": titulo,
            "subtitulo": subtitulo,
            "data": data,
            "profissional": profissional,
            "origem": origem,
            "cards": cards or [],
            "conteudo": conteudo or [],
            "interpretacao": interpretacao,
            "conduta": conduta,
        }

    @abstractmethod
    def build_response(self, db, evento_id):
        pass