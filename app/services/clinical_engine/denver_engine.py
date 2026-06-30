class DenverEngine:
    instrumento = "DENVER"
    versao = "1.0"

    DOMINIOS = {
        "ps": "Pessoal-social",
        "mf": "Motor fino-adaptativo",
        "lg": "Linguagem",
        "mg": "Motor grosso",
    }

    def execute(self, context):
        respostas = context.respostas or {}

        resultado_dominios = {}
        total_falhas = 0
        total_recusas = 0
        total_nao_observado = 0
        total_itens_validos = 0

        for prefixo, nome in self.DOMINIOS.items():
            itens = {
                campo: valor
                for campo, valor in respostas.items()
                if campo.startswith(f"{prefixo}_")
            }

            passou = sum(1 for v in itens.values() if v == "PASSOU")
            falhou = sum(1 for v in itens.values() if v == "FALHOU")
            recusou = sum(1 for v in itens.values() if v == "RECUSOU")
            nao_observado = sum(1 for v in itens.values() if v == "NAO_OBSERVADO")

            validos = passou + falhou

            total_falhas += falhou
            total_recusas += recusou
            total_nao_observado += nao_observado
            total_itens_validos += validos

            resultado_dominios[prefixo] = {
                "dominio": nome,
                "passou": passou,
                "falhou": falhou,
                "recusou": recusou,
                "nao_observado": nao_observado,
                "itens_validos": validos,
                "status": self._classificar_dominio(falhou, validos),
            }

        classificacao = self._classificar_geral(
            total_falhas=total_falhas,
            total_recusas=total_recusas,
            total_nao_observado=total_nao_observado,
            total_itens_validos=total_itens_validos,
        )

        score = total_falhas

        conduta = self._gerar_conduta(classificacao)

        interpretacao = self._gerar_interpretacao(
            classificacao=classificacao,
            total_falhas=total_falhas,
            total_recusas=total_recusas,
            total_nao_observado=total_nao_observado,
            resultado_dominios=resultado_dominios,
        )

        alertas = self._gerar_alertas(
            total_falhas=total_falhas,
            total_recusas=total_recusas,
            total_nao_observado=total_nao_observado,
            resultado_dominios=resultado_dominios,
        )

        return {
            "instrumento": self.instrumento,
            "versao": self.versao,
            "score": score,
            "score_texto": str(score),
            "classificacao": classificacao,
            "conduta": conduta,
            "interpretacao": interpretacao,
            "alertas": alertas,
            "resultado": {
                "dominios": resultado_dominios,
                "total_falhas": total_falhas,
                "total_recusas": total_recusas,
                "total_nao_observado": total_nao_observado,
                "total_itens_validos": total_itens_validos,
            },
        }

    def _classificar_dominio(self, falhas, validos):
        if validos == 0:
            return "Não avaliado"

        if falhas == 0:
            return "Adequado"

        if falhas == 1:
            return "Atenção"

        return "Atraso"

    def _classificar_geral(
        self,
        total_falhas,
        total_recusas,
        total_nao_observado,
        total_itens_validos,
    ):
        if total_itens_validos == 0:
            return "Não conclusivo"

        if total_falhas >= 4:
            return "Atraso"

        if total_falhas >= 2:
            return "Suspeito"

        if total_falhas == 1:
            return "Atenção"

        if total_recusas >= 2 or total_nao_observado >= 3:
            return "Não conclusivo"

        return "Adequado"

    def _gerar_conduta(self, classificacao):
        if classificacao == "Adequado":
            return "Manter acompanhamento de rotina e vigilância do desenvolvimento."

        if classificacao == "Atenção":
            return "Reforçar vigilância do desenvolvimento e considerar reavaliação em curto intervalo."

        if classificacao == "Suspeito":
            return "Recomenda-se avaliação clínica complementar e acompanhamento multiprofissional."

        if classificacao == "Atraso":
            return "Recomenda-se avaliação multiprofissional prioritária e elaboração de plano terapêutico."

        return "Avaliação não conclusiva. Recomenda-se repetir o instrumento com observação clínica adequada."

    def _gerar_interpretacao(
        self,
        classificacao,
        total_falhas,
        total_recusas,
        total_nao_observado,
        resultado_dominios,
    ):
        dominios_afetados = [
            d["dominio"]
            for d in resultado_dominios.values()
            if d["falhou"] > 0
        ]

        if not dominios_afetados:
            return (
                f"Denver II v1.0 com classificação {classificacao}. "
                "Não foram identificadas falhas nos itens avaliados."
            )

        return (
            f"Denver II v1.0 com classificação {classificacao}. "
            f"Foram identificadas {total_falhas} falha(s), "
            f"{total_recusas} recusa(s) e "
            f"{total_nao_observado} item(ns) não observado(s). "
            f"Domínios com falhas: {', '.join(dominios_afetados)}."
        )

    def _gerar_alertas(
        self,
        total_falhas,
        total_recusas,
        total_nao_observado,
        resultado_dominios,
    ):
        alertas = []

        for dominio in resultado_dominios.values():
            if dominio["status"] == "Atraso":
                alertas.append(
                    f"Atenção para possível atraso no domínio {dominio['dominio']}."
                )

        if total_recusas >= 2:
            alertas.append(
                "Número elevado de recusas pode reduzir a confiabilidade da avaliação."
            )

        if total_nao_observado >= 3:
            alertas.append(
                "Muitos itens não observados. Recomenda-se repetir a avaliação."
            )

        return alertas