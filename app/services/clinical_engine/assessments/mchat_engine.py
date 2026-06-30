from app.services.clinical_engine.base_engine import BaseAssessmentEngine


class MChatEngine(BaseAssessmentEngine):
    instrumento = "MCHAT"
    versao = "1.0"

    RESPOSTAS_RISCO = {
        1: "NAO",
        2: "NAO",
        3: "NAO",
        4: "NAO",
        5: "NAO",
        6: "NAO",
        7: "NAO",
        8: "NAO",
        9: "NAO",
        10: "NAO",
        11: "SIM",
        12: "NAO",
        13: "NAO",
        14: "NAO",
        15: "NAO",
        16: "NAO",
        17: "NAO",
        18: "NAO",
        19: "NAO",
        20: "NAO",
    }

    def executar(self, context):
        respostas_mchat = {}

        for campo, valor in context.respostas.items():
            if str(campo).startswith("mchat_"):
                numero = int(str(campo).replace("mchat_", ""))
                respostas_mchat[numero] = valor

        score = 0
        itens_risco = []
        alertas = []

        for item, resposta_risco in self.RESPOSTAS_RISCO.items():
            resposta = respostas_mchat.get(item)

            if resposta is None:
                resposta = respostas_mchat.get(str(item))

            if resposta is None:
                continue

            resposta_normalizada = str(resposta).strip().upper()

            if resposta_normalizada == resposta_risco:
                score += 1
                itens_risco.append(item)

        if score <= 2:
            classificacao = "Baixo risco"
            conduta = "Manter acompanhamento de rotina e vigilância do desenvolvimento."
        elif 3 <= score <= 7:
            classificacao = "Risco moderado"
            conduta = "Aplicar entrevista de seguimento do M-CHAT-R/F e considerar encaminhamento conforme avaliação clínica."
        else:
            classificacao = "Alto risco"
            conduta = "Encaminhar para avaliação especializada e iniciar investigação diagnóstica."

        if score >= 3:
            alertas.append("Triagem positiva para risco de TEA.")

        if score >= 8:
            alertas.append("Risco elevado. Recomendado encaminhamento especializado.")

        return {
            "instrumento": self.instrumento,
            "versao": self.versao,
            "score": score,
            "classificacao": classificacao,
            "conduta": conduta,
            "interpretacao": self._gerar_interpretacao(score, classificacao, itens_risco),
            "dominios": {
                "itens_risco": itens_risco,
                "total_itens_risco": len(itens_risco)
            },
            "alertas": alertas,
            "metadata": {
                "engine": "mchat_engine",
                "engine_version": self.versao
            }
        }

    def _gerar_interpretacao(self, score: int, classificacao: str, itens_risco: list) -> str:
        if not itens_risco:
            return (
                f"M-CHAT com score {score}, classificado como {classificacao}. "
                "Não foram identificados itens críticos de risco nesta avaliação."
            )

        return (
            f"M-CHAT com score {score}, classificado como {classificacao}. "
            f"Foram identificados sinais de risco nos itens: {', '.join(map(str, itens_risco))}."
        )