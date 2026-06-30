from app.services.clinical_engine.base_engine import BaseAssessmentEngine


class DenverEngine(BaseAssessmentEngine):
    instrumento = "DENVER"
    versao = "1.0"

    DOMINIOS = {
        "ps": "Pessoal-social",
        "mf": "Motor fino-adaptativo",
        "lg": "Linguagem",
        "mg": "Motor grosso",
    }

    def executar(self, context):

        dominios = {}

        total_falhas = 0
        total_passou = 0
        total_recusou = 0
        total_nao_observado = 0

        for prefixo, nome in self.DOMINIOS.items():

            passou = 0
            falhou = 0
            recusou = 0
            nao_observado = 0

            for campo, valor in context.respostas.items():

                if not str(campo).startswith(prefixo + "_"):
                    continue

                valor = str(valor).upper()

                if valor == "PASSOU":
                    passou += 1

                elif valor == "FALHOU":
                    falhou += 1

                elif valor == "RECUSOU":
                    recusou += 1

                elif valor == "NAO_OBSERVADO":
                    nao_observado += 1

            dominios[prefixo] = {
                "dominio": nome,
                "passou": passou,
                "falhou": falhou,
                "recusou": recusou,
                "nao_observado": nao_observado,
            }

            total_passou += passou
            total_falhas += falhou
            total_recusou += recusou
            total_nao_observado += nao_observado

        classificacao = self._classificar(total_falhas)

        return {

            "instrumento": self.instrumento,

            "versao": self.versao,

            "score": total_falhas,

            "classificacao": classificacao,

            "conduta": self._conduta(classificacao),

            "interpretacao": self._interpretacao(
                classificacao,
                total_falhas,
                dominios
            ),

            "dominios": dominios,

            "alertas": self._alertas(
                total_falhas,
                dominios
            ),

            "metadata": {

                "engine": "denver_engine",

                "engine_version": self.versao

            }

        }

    def _classificar(self, falhas):

        if falhas == 0:
            return "Adequado"

        if falhas <= 2:
            return "Atenção"

        if falhas <= 4:
            return "Suspeito"

        return "Atraso"

    def _conduta(self, classificacao):

        if classificacao == "Adequado":
            return "Desenvolvimento compatível com os itens avaliados."

        if classificacao == "Atenção":
            return "Reavaliar em curto prazo e manter acompanhamento."

        if classificacao == "Suspeito":
            return "Recomenda-se avaliação complementar."

        return "Encaminhar para avaliação multiprofissional."

    def _interpretacao(
        self,
        classificacao,
        falhas,
        dominios
    ):

        dominios_alterados = []

        for dominio in dominios.values():

            if dominio["falhou"] > 0:

                dominios_alterados.append(
                    dominio["dominio"]
                )

        if not dominios_alterados:

            return (
                f"Denver II com classificação {classificacao}. "
                "Não foram identificadas alterações nos itens avaliados."
            )

        return (

            f"Denver II com classificação {classificacao}. "

            f"Foram observadas {falhas} falha(s). "

            f"Domínios envolvidos: "

            f"{', '.join(dominios_alterados)}."

        )

    def _alertas(
        self,
        falhas,
        dominios
    ):

        alertas = []

        if falhas >= 3:

            alertas.append(
                "Avaliação sugere necessidade de investigação complementar."
            )

        for dominio in dominios.values():

            if dominio["falhou"] >= 2:

                alertas.append(
                    f"Alterações predominantes em {dominio['dominio']}."
                )

        return alertas