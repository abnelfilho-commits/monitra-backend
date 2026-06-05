from dotenv import load_dotenv

load_dotenv()

from datetime import date, datetime, timedelta
import random

from sqlalchemy import text
from app.database import SessionLocal


CLINICA_NOME = "Centro Integrado de Saúde Longitudinal"
PROFISSIONAL_NOME = "Dra. Helena Martins"
LIMPAR_DEMO_ANTES = True

db = SessionLocal()


def classificar_risco(score: int) -> str:
    if score <= 3:
        return "baixo"
    if score <= 6:
        return "moderado"
    if score <= 8:
        return "alto"
    return "critico"


def definir_protocolo(score: int) -> str:
    if score <= 3:
        return "Acompanhamento de rotina"
    if score <= 6:
        return "Monitoramento intensificado"
    if score <= 8:
        return "Intervenção clínica prioritária"
    return "Alerta crítico / busca ativa imediata"


def leitura_clinica(dados, score):
    risco = classificar_risco(score)

    partes = [
        f"Paciente com risco {risco.upper()} e score clínico {score}/10.",
    ]

    if dados["glicemia_jejum"] >= 180:
        partes.append("Glicemia de jejum persistentemente elevada.")
    elif dados["glicemia_jejum"] >= 126:
        partes.append("Glicemia acima da meta, exigindo acompanhamento.")

    if dados["pressao_sistolica"] >= 160 or dados["pressao_diastolica"] >= 100:
        partes.append("Pressão arterial em faixa de alerta.")
    elif dados["pressao_sistolica"] >= 140 or dados["pressao_diastolica"] >= 90:
        partes.append("Pressão arterial acima do desejável.")

    if not dados["uso_medicacao"]:
        partes.append("Baixa adesão medicamentosa registrada.")

    if not dados["adesao_alimentar"]:
        partes.append("Adesão alimentar inadequada.")

    if dados["fadiga"] or dados["tontura"] or dados["cefaleia"]:
        partes.append("Sintomas associados presentes no período.")

    if dados["sono"] in ["ruim", "muito_ruim"]:
        partes.append("Sono prejudicado, podendo influenciar o controle metabólico.")

    return " ".join(partes)


def calcular_score(dados):
    score = 0

    glicemia = dados["glicemia_jejum"]
    sistolica = dados["pressao_sistolica"]
    diastolica = dados["pressao_diastolica"]

    if glicemia >= 250:
        score += 4
    elif glicemia >= 180:
        score += 3
    elif glicemia >= 126:
        score += 2
    elif glicemia >= 110:
        score += 1

    if sistolica >= 180 or diastolica >= 110:
        score += 4
    elif sistolica >= 160 or diastolica >= 100:
        score += 3
    elif sistolica >= 140 or diastolica >= 90:
        score += 2
    elif sistolica >= 130 or diastolica >= 85:
        score += 1

    if dados["peso"] >= dados["peso_alerta"]:
        score += 1

    if not dados["uso_medicacao"]:
        score += 1

    if not dados["adesao_alimentar"]:
        score += 1

    if dados["fadiga"]:
        score += 1

    if dados["tontura"]:
        score += 1

    if dados["cefaleia"]:
        score += 1

    if dados["sono"] in ["ruim", "muito_ruim"]:
        score += 1

    return min(score, 10)


PACIENTES = [
    ("João Carlos Ribeiro", "M", "1968-04-12", "controlado", ["hipertensao"]),
    ("Maria Helena Souza", "F", "1972-09-20", "controlado", ["diabetes_tipo_2"]),
    ("Carlos Eduardo Lima", "M", "1965-01-08", "controlado", ["hipertensao", "resistencia_insulinica"]),
    ("Ana Paula Moreira", "F", "1980-07-18", "controlado", ["pre_diabetes"]),

    ("Roberto Almeida", "M", "1960-11-02", "moderado", ["diabetes_tipo_2", "hipertensao"]),
    ("Sueli Cristina Dias", "F", "1975-03-27", "moderado", ["obesidade_visceral", "hipertensao"]),
    ("Marcos Vinicius Prado", "M", "1969-08-14", "moderado", ["sindrome_metabolica"]),
    ("Patricia Fernandes", "F", "1983-12-05", "moderado", ["diabetes_tipo_2"]),

    ("Antônio Ribeiro Neto", "M", "1958-06-30", "alto_risco", ["diabetes_tipo_2", "hipertensao"]),
    ("Regina Célia Barros", "F", "1962-02-16", "alto_risco", ["sindrome_metabolica", "obesidade_visceral"]),
    ("José Aparecido Mendes", "M", "1955-10-09", "alto_risco", ["diabetes_tipo_2", "hipertensao", "obesidade_visceral"]),
    ("Claudia Regina Lopes", "F", "1970-05-25", "alto_risco", ["hipertensao", "resistencia_insulinica"]),

    ("Sebastião Oliveira", "M", "1951-01-22", "critico", ["diabetes_tipo_2", "hipertensao", "sindrome_metabolica"]),
    ("Marta Aparecida Nunes", "F", "1959-04-01", "critico", ["diabetes_tipo_2", "obesidade_visceral"]),
    ("Nelson Pereira Duarte", "M", "1954-09-11", "critico", ["diabetes_tipo_2", "hipertensao"]),

    ("Luciana Martins Rocha", "F", "1978-06-19", "melhora", ["diabetes_tipo_2", "hipertensao"]),
    ("Fernando Henrique Costa", "M", "1974-02-08", "melhora", ["sindrome_metabolica"]),
    ("Eliane Cristina Moura", "F", "1981-10-17", "melhora", ["obesidade_visceral", "resistencia_insulinica"]),

    ("Paulo Sérgio Batista", "M", "1967-12-28", "abandono", ["diabetes_tipo_2", "hipertensao"]),
    ("Rosângela Ferreira Lima", "F", "1971-07-04", "abandono", ["hipertensao", "obesidade_visceral"]),
]


BASES = {
    "controlado": dict(peso=78, glicemia=105, sistolica=124, diastolica=78),
    "moderado": dict(peso=92, glicemia=145, sistolica=142, diastolica=90),
    "alto_risco": dict(peso=108, glicemia=190, sistolica=160, diastolica=98),
    "critico": dict(peso=118, glicemia=250, sistolica=178, diastolica=108),
    "melhora": dict(peso=112, glicemia=220, sistolica=165, diastolica=100),
    "abandono": dict(peso=106, glicemia=180, sistolica=155, diastolica=96),
}


def limpar_demo():
    pacientes_ids = db.execute(text("""
        SELECT id FROM pacientes
        WHERE clinica_id = (
            SELECT id FROM clinicas WHERE nome = :nome
        )
    """), {"nome": CLINICA_NOME}).fetchall()

    ids = [p.id for p in pacientes_ids]

    if not ids:
        db.execute(text("DELETE FROM profissionais WHERE nome = :nome"), {"nome": PROFISSIONAL_NOME})
        db.execute(text("DELETE FROM clinicas WHERE nome = :nome"), {"nome": CLINICA_NOME})
        return

    db.execute(text("DELETE FROM intervencoes_cardiometabolicas WHERE paciente_id = ANY(:ids)"), {"ids": ids})
    db.execute(text("DELETE FROM paciente_condicoes_clinicas WHERE paciente_id = ANY(:ids)"), {"ids": ids})
    db.execute(text("DELETE FROM paciente_modulos WHERE paciente_id = ANY(:ids)"), {"ids": ids})
    db.execute(text("""
        DELETE FROM respostas_registro
        WHERE registro_id IN (
            SELECT id FROM registros_longitudinais WHERE paciente_id = ANY(:ids)
        )
    """), {"ids": ids})
    db.execute(text("DELETE FROM registros_longitudinais WHERE paciente_id = ANY(:ids)"), {"ids": ids})
    db.execute(text("DELETE FROM pacientes WHERE id = ANY(:ids)"), {"ids": ids})
    db.execute(text("DELETE FROM profissionais WHERE nome = :nome"), {"nome": PROFISSIONAL_NOME})
    db.execute(text("DELETE FROM clinicas WHERE nome = :nome"), {"nome": CLINICA_NOME})


try:
    if LIMPAR_DEMO_ANTES:
        limpar_demo()
        db.commit()

    modulo = db.execute(text("""
        SELECT id FROM modulos_clinicos
        WHERE slug = 'cardiometabolico'
    """)).fetchone()

    if not modulo:
        raise Exception("Módulo cardiometabólico não encontrado.")

    modulo_id = modulo.id

    formulario = db.execute(text("""
        SELECT id FROM formularios_modulo
        WHERE modulo_id = :modulo_id
        AND tipo = 'registro_diario'
        LIMIT 1
    """), {"modulo_id": modulo_id}).fetchone()

    if not formulario:
        raise Exception("Formulário de registro diário cardiometabólico não encontrado.")

    formulario_id = formulario.id

    clinica = db.execute(text("""
        INSERT INTO clinicas (nome, cnpj, email, telefone, ativa)
        VALUES (:nome, NULL, 'contato@saudelongitudinal.com.br', '(65) 3000-1000', true)
        RETURNING id
    """), {"nome": CLINICA_NOME}).fetchone()

    clinica_id = clinica.id

    profissional = db.execute(text("""
        INSERT INTO profissionais (nome, email, especialidade, clinica_id, ativo)
        VALUES (:nome, 'helena.martins@saudelongitudinal.com.br', 'Cardiologia / Saúde da Família', :clinica_id, true)
        RETURNING id
    """), {
        "nome": PROFISSIONAL_NOME,
        "clinica_id": clinica_id
    }).fetchone()

    profissional_id = profissional.id

    hoje = date.today()

    for nome, genero, nascimento, perfil, condicoes in PACIENTES:
        paciente = db.execute(text("""
            INSERT INTO pacientes (
                nome,
                data_nascimento,
                genero,
                clinica_id,
                profissional_id,
                ativo
            )
            VALUES (
                :nome,
                :data_nascimento,
                :genero,
                :clinica_id,
                :profissional_id,
                true
            )
            RETURNING id
        """), {
            "nome": nome,
            "data_nascimento": nascimento,
            "genero": genero,
            "clinica_id": clinica_id,
            "profissional_id": profissional_id
        }).fetchone()

        paciente_id = paciente.id

        db.execute(text("""
            INSERT INTO paciente_modulos (paciente_id, modulo_id, ativo)
            VALUES (:paciente_id, :modulo_id, true)
        """), {
            "paciente_id": paciente_id,
            "modulo_id": modulo_id
        })

        for condicao in condicoes:
            db.execute(text("""
                INSERT INTO paciente_condicoes_clinicas (
                    paciente_id,
                    modulo_id,
                    condicao,
                    ativo
                )
                VALUES (
                    :paciente_id,
                    :modulo_id,
                    :condicao,
                    true
                )
            """), {
                "paciente_id": paciente_id,
                "modulo_id": modulo_id,
                "condicao": condicao
            })

        base = BASES[perfil]
        peso_alerta = base["peso"] + 2

        for dia in range(90):
            data_registro = hoje - timedelta(days=89 - dia)

            if perfil == "abandono" and dia > 45 and random.random() < 0.55:
                continue

            fator = dia / 89

            if perfil == "controlado":
                glicemia = base["glicemia"] + random.uniform(-8, 10)
                sistolica = base["sistolica"] + random.uniform(-6, 7)
                diastolica = base["diastolica"] + random.uniform(-4, 5)
                peso = base["peso"] + random.uniform(-1.2, 1.2)
                adesao = random.random() > 0.08
                medicacao = random.random() > 0.04

            elif perfil == "moderado":
                glicemia = base["glicemia"] + random.uniform(-20, 35)
                sistolica = base["sistolica"] + random.uniform(-10, 18)
                diastolica = base["diastolica"] + random.uniform(-6, 10)
                peso = base["peso"] + random.uniform(-1.5, 2.5)
                adesao = random.random() > 0.25
                medicacao = random.random() > 0.18

            elif perfil == "alto_risco":
                glicemia = base["glicemia"] + random.uniform(-15, 55) + fator * 12
                sistolica = base["sistolica"] + random.uniform(-8, 25)
                diastolica = base["diastolica"] + random.uniform(-5, 14)
                peso = base["peso"] + fator * 2.5 + random.uniform(-1, 2)
                adesao = random.random() > 0.45
                medicacao = random.random() > 0.32

            elif perfil == "critico":
                glicemia = base["glicemia"] + random.uniform(-25, 70)
                sistolica = base["sistolica"] + random.uniform(-10, 30)
                diastolica = base["diastolica"] + random.uniform(-6, 18)
                peso = base["peso"] + random.uniform(-1, 3)
                adesao = random.random() > 0.60
                medicacao = random.random() > 0.50

            elif perfil == "melhora":
                glicemia = base["glicemia"] - fator * 85 + random.uniform(-12, 18)
                sistolica = base["sistolica"] - fator * 32 + random.uniform(-8, 10)
                diastolica = base["diastolica"] - fator * 18 + random.uniform(-5, 6)
                peso = base["peso"] - fator * 6 + random.uniform(-1, 1)
                adesao = random.random() > (0.45 - fator * 0.35)
                medicacao = random.random() > (0.35 - fator * 0.28)

            else:
                glicemia = base["glicemia"] + fator * 55 + random.uniform(-20, 35)
                sistolica = base["sistolica"] + fator * 28 + random.uniform(-10, 18)
                diastolica = base["diastolica"] + fator * 15 + random.uniform(-5, 12)
                peso = base["peso"] + fator * 4 + random.uniform(-1, 2)
                adesao = random.random() > 0.70
                medicacao = random.random() > 0.62

            glicemia_pos = glicemia + random.uniform(25, 65)

            sono = random.choices(
                ["bom", "regular", "ruim", "muito_ruim"],
                weights=[35, 35, 22, 8] if perfil not in ["critico", "abandono"] else [10, 25, 40, 25]
            )[0]

            humor = random.choices(
                ["estavel", "ansioso", "irritado", "desanimado"],
                weights=[45, 25, 18, 12] if perfil not in ["critico", "abandono"] else [15, 30, 25, 30]
            )[0]

            atividade = random.choices(
                ["nenhuma", "leve", "moderada", "intensa"],
                weights=[45, 35, 18, 2] if perfil in ["alto_risco", "critico", "abandono"] else [20, 45, 30, 5]
            )[0]

            fadiga = random.random() < (0.55 if perfil in ["critico", "abandono"] else 0.20)
            tontura = random.random() < (0.40 if perfil in ["critico", "alto_risco"] else 0.12)
            cefaleia = random.random() < (0.38 if perfil in ["critico", "alto_risco", "abandono"] else 0.15)
            dor = random.random() < (0.25 if perfil in ["critico", "abandono"] else 0.08)

            dados = {
                "glicemia_jejum": round(glicemia),
                "glicemia_pos_prandial": round(glicemia_pos),
                "pressao_sistolica": round(sistolica),
                "pressao_diastolica": round(diastolica),
                "peso": round(peso, 1),
                "peso_alerta": peso_alerta,
                "uso_medicacao": medicacao,
                "adesao_alimentar": adesao,
                "fadiga": fadiga,
                "tontura": tontura,
                "cefaleia": cefaleia,
                "sono": sono,
            }

            score = calcular_score(dados)
            risco = classificar_risco(score)
            protocolo = definir_protocolo(score)
            leitura = leitura_clinica(dados, score)

            observacoes = None
            if risco == "critico":
                observacoes = "Paciente com sinais de descompensação clínica. Recomendada busca ativa e reavaliação prioritária."
            elif perfil == "melhora" and dia > 60:
                observacoes = "Evolução favorável após intervenção, com melhora de adesão e redução progressiva do risco."
            elif perfil == "abandono" and dia > 50:
                observacoes = "Registro irregular e baixa adesão. Necessária estratégia de busca ativa."

            db.execute(text("""
                INSERT INTO registros_longitudinais (
                    paciente_id,
                    modulo_id,
                    formulario_id,
                    origem,
                    data_registro,
                    modulo,
                    glicemia_jejum,
                    glicemia_pos_prandial,
                    pressao_sistolica,
                    pressao_diastolica,
                    peso,
                    ingestao_hidrica,
                    atividade_fisica,
                    humor,
                    sono,
                    fadiga,
                    dor,
                    uso_medicacao,
                    adesao_alimentar,
                    tontura,
                    cefaleia,
                    observacoes,
                    score_clinico,
                    risco,
                    protocolo,
                    leitura_clinica
                )
                VALUES (
                    :paciente_id,
                    :modulo_id,
                    :formulario_id,
                    'PROFISSIONAL',
                    :data_registro,
                    'cardiometabolico',
                    :glicemia_jejum,
                    :glicemia_pos_prandial,
                    :pressao_sistolica,
                    :pressao_diastolica,
                    :peso,
                    :ingestao_hidrica,
                    :atividade_fisica,
                    :humor,
                    :sono,
                    :fadiga,
                    :dor,
                    :uso_medicacao,
                    :adesao_alimentar,
                    :tontura,
                    :cefaleia,
                    :observacoes,
                    :score_clinico,
                    :risco,
                    :protocolo,
                    :leitura_clinica
                )
            """), {
                "paciente_id": paciente_id,
                "modulo_id": modulo_id,
                "formulario_id": formulario_id,
                "data_registro": data_registro,
                "glicemia_jejum": dados["glicemia_jejum"],
                "glicemia_pos_prandial": dados["glicemia_pos_prandial"],
                "pressao_sistolica": dados["pressao_sistolica"],
                "pressao_diastolica": dados["pressao_diastolica"],
                "peso": dados["peso"],
                "ingestao_hidrica": round(random.uniform(1.1, 2.8), 1),
                "atividade_fisica": atividade,
                "humor": humor,
                "sono": sono,
                "fadiga": fadiga,
                "dor": dor,
                "uso_medicacao": medicacao,
                "adesao_alimentar": adesao,
                "tontura": tontura,
                "cefaleia": cefaleia,
                "observacoes": observacoes,
                "score_clinico": score,
                "risco": risco,
                "protocolo": protocolo,
                "leitura_clinica": leitura,
            })

        intervencoes = []

        if perfil == "controlado":
            intervencoes = [
                ("Acompanhamento preventivo", "Manter rotina de monitoramento e reforçar autocuidado.", "baixa", 70),
                ("Educação em saúde", "Orientação sobre manutenção de alimentação adequada e atividade física.", "baixa", 35),
            ]

        elif perfil == "moderado":
            intervencoes = [
                ("Ajuste de plano terapêutico", "Reforçada adesão medicamentosa e metas glicêmicas.", "moderada", 65),
                ("Encaminhamento nutricional", "Plano alimentar individualizado para redução de risco cardiometabólico.", "moderada", 45),
                ("Monitoramento intensificado", "Reavaliar curva glicêmica e pressão arterial em 15 dias.", "moderada", 25),
            ]

        elif perfil == "alto_risco":
            intervencoes = [
                ("Alerta de risco elevado", "Paciente com recorrência de glicemia e pressão acima da meta.", "alta", 75),
                ("Busca ativa", "Contato realizado para reforço de adesão e avaliação de sintomas.", "alta", 55),
                ("Reavaliação clínica", "Solicitada consulta antecipada para revisão terapêutica.", "alta", 35),
                ("Encaminhamento multiprofissional", "Encaminhamento para nutrição e educação em diabetes.", "moderada", 20),
            ]

        elif perfil == "critico":
            intervencoes = [
                ("Alerta crítico", "Paciente com sinais persistentes de descompensação cardiometabólica.", "critica", 80),
                ("Busca ativa imediata", "Equipe orientada a contato prioritário com paciente/família.", "critica", 60),
                ("Reavaliação urgente", "Recomendado atendimento clínico prioritário para revisão de conduta.", "critica", 40),
                ("Plano intensivo de cuidado", "Definido acompanhamento próximo por risco de agravamento.", "alta", 20),
            ]

        elif perfil == "melhora":
            intervencoes = [
                ("Intervenção inicial", "Paciente iniciou acompanhamento por risco cardiometabólico elevado.", "alta", 80),
                ("Ajuste terapêutico", "Reforçada adesão medicamentosa, dieta e rotina de atividade física.", "alta", 60),
                ("Retorno de acompanhamento", "Evolução favorável, com melhora de glicemia, pressão e peso.", "moderada", 35),
                ("Manutenção do plano", "Paciente segue em melhora progressiva com redução de risco.", "baixa", 12),
            ]

        elif perfil == "abandono":
            intervencoes = [
                ("Baixa adesão", "Paciente apresenta falhas recorrentes de registro e acompanhamento.", "alta", 70),
                ("Busca ativa", "Tentativa de contato para retomada do cuidado longitudinal.", "alta", 45),
                ("Risco de abandono", "Paciente com ausência parcial de registros e piora dos indicadores.", "critica", 20),
            ]

        for tipo, descricao, prioridade, dias_atras in intervencoes:
            db.execute(text("""
                INSERT INTO intervencoes_cardiometabolicas (
                    paciente_id,
                    profissional_id,
                    tipo,
                    descricao,
                    prioridade,
                    created_at
                )
                VALUES (
                    :paciente_id,
                    :profissional_id,
                    :tipo,
                    :descricao,
                    :prioridade,
                    :created_at
                )
            """), {
                "paciente_id": paciente_id,
                "profissional_id": profissional_id,
                "tipo": tipo,
                "descricao": descricao,
                "prioridade": prioridade,
                "created_at": datetime.now() - timedelta(days=dias_atras)
            })

    db.commit()

    print("Seed demo cardiometabólico criado com sucesso.")
    print(f"Clínica: {CLINICA_NOME}")
    print("Pacientes criados:", len(PACIENTES))

except Exception as e:
    db.rollback()
    print(f"Erro ao executar seed demo cardiometabólico: {e}")
    raise

finally:
    db.close()