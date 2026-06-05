from app.database import SessionLocal
from sqlalchemy import text


db = SessionLocal()

try:
    # 1. Módulos clínicos
    modulos = [
        ("Neurodesenvolvimento", "neurodesenvolvimento", "Módulo legado atual do Monitra para TEA/TDAH."),
        ("Cardiometabólico", "cardiometabolico", "Módulo para DM1, DM2, hipertensão e risco cardiometabólico."),
        ("Idoso", "idoso", "Módulo futuro para cuidado longitudinal da pessoa idosa."),
        ("Reabilitação", "reabilitacao", "Módulo futuro para acompanhamento de reabilitação."),
        ("Saúde Mental", "saude_mental", "Módulo futuro para saúde mental."),
        ("Obesidade", "obesidade", "Módulo futuro para obesidade."),
        ("Atenção Primária", "atencao_primaria", "Módulo futuro para atenção primária."),
    ]

    for nome, slug, descricao in modulos:
        db.execute(
            text("""
                INSERT INTO modulos_clinicos (nome, slug, descricao, ativo)
                VALUES (:nome, :slug, :descricao, true)
                ON CONFLICT (slug) DO NOTHING
            """),
            {"nome": nome, "slug": slug, "descricao": descricao}
        )

    db.commit()

    # 2. Buscar ID do Cardiometabólico
    cardiometabolico = db.execute(
        text("SELECT id FROM modulos_clinicos WHERE slug = 'cardiometabolico'")
    ).fetchone()

    if not cardiometabolico:
        raise Exception("Módulo cardiometabólico não encontrado.")

    modulo_id = cardiometabolico[0]

    # 3. Criar formulário diário do Cardiometabólico
    db.execute(
        text("""
            INSERT INTO formularios_modulo (modulo_id, nome, tipo, ativo)
            SELECT :modulo_id, 'Registro Diário Cardiometabólico', 'registro_diario', true
            WHERE NOT EXISTS (
                SELECT 1 FROM formularios_modulo
                WHERE modulo_id = :modulo_id
                AND tipo = 'registro_diario'
            )
        """),
        {"modulo_id": modulo_id}
    )

    db.commit()

    formulario = db.execute(
        text("""
            SELECT id FROM formularios_modulo
            WHERE modulo_id = :modulo_id
            AND tipo = 'registro_diario'
        """),
        {"modulo_id": modulo_id}
    ).fetchone()

    formulario_id = formulario[0]

    # 4. Campos iniciais do formulário
    campos = [
        # Base comum
        ("qualidade_sono", "Como foi a qualidade do sono?", "escala", False, 1, None, None),
        ("alimentacao_adequada", "A alimentação foi adequada hoje?", "booleano", False, 2, None, None),
        ("hidratacao_adequada", "A hidratação foi adequada hoje?", "booleano", False, 3, None, None),
        ("atividade_fisica", "Realizou atividade física hoje?", "booleano", False, 4, None, None),
        ("estresse", "Nível de estresse no dia", "escala", False, 5, None, None),
        ("sintomas_gerais", "Sintomas gerais observados", "textarea", False, 6, None, None),
        ("intercorrencias", "Houve alguma intercorrência?", "textarea", False, 7, None, None),

        # Cardiometabólico adquirido
        ("glicemia_jejum", "Glicemia de jejum", "numero", False, 20, None, '{"condicoes":["diabetes_tipo_2","pre_diabetes","resistencia_insulinica","sindrome_metabolica"]}'),
        ("glicemia_pos_prandial", "Glicemia pós-prandial", "numero", False, 21, None, '{"condicoes":["diabetes_tipo_2","pre_diabetes","resistencia_insulinica","sindrome_metabolica"]}'),
        ("compulsao_alimentar", "Teve compulsão alimentar?", "booleano", False, 22, None, '{"condicoes":["diabetes_tipo_2","obesidade_visceral","sindrome_metabolica"]}'),
        ("desejo_acucar", "Teve desejo intenso por açúcar?", "booleano", False, 23, None, '{"condicoes":["diabetes_tipo_2","obesidade_visceral","sindrome_metabolica"]}'),
        ("sonolencia_pos_prandial", "Teve sonolência após refeição?", "booleano", False, 24, None, '{"condicoes":["diabetes_tipo_2","resistencia_insulinica"]}'),

        # Pressão arterial
        ("pressao_sistolica", "Pressão sistólica", "numero", False, 40, None, '{"condicoes":["hipertensao","dm1_com_hipertensao"]}'),
        ("pressao_diastolica", "Pressão diastólica", "numero", False, 41, None, '{"condicoes":["hipertensao","dm1_com_hipertensao"]}'),
        ("cefaleia", "Teve dor de cabeça?", "booleano", False, 42, None, '{"condicoes":["hipertensao","dm1_com_hipertensao"]}'),
        ("tontura", "Teve tontura?", "booleano", False, 43, None, '{"condicoes":["hipertensao","dm1_com_hipertensao"]}'),
        ("uso_correto_medicacao", "Usou corretamente a medicação?", "booleano", False, 44, None, '{"condicoes":["hipertensao","diabetes_tipo_2","dm1_com_hipertensao"]}'),

        # DM1
        ("glicemia_capilar", "Glicemia capilar ou sensor", "numero", False, 60, None, '{"condicoes":["diabetes_tipo_1","dm1_com_hipertensao"]}'),
        ("hipoglicemia", "Teve hipoglicemia?", "booleano", False, 61, None, '{"condicoes":["diabetes_tipo_1","dm1_com_hipertensao"]}'),
        ("hiperglicemia", "Teve hiperglicemia?", "booleano", False, 62, None, '{"condicoes":["diabetes_tipo_1","dm1_com_hipertensao"]}'),
        ("insulina_basal", "Dose de insulina basal", "numero", False, 63, None, '{"condicoes":["diabetes_tipo_1","dm1_com_hipertensao"]}'),
        ("insulina_rapida", "Dose de insulina rápida/correção", "numero", False, 64, None, '{"condicoes":["diabetes_tipo_1","dm1_com_hipertensao"]}'),
        ("febre", "Teve febre?", "booleano", False, 65, None, '{"condicoes":["diabetes_tipo_1","dm1_com_hipertensao"]}'),
        ("infeccao", "Teve infecção recente?", "booleano", False, 66, None, '{"condicoes":["diabetes_tipo_1","dm1_com_hipertensao"]}'),
        ("cetonas", "Houve presença de cetonas?", "booleano", False, 67, None, '{"condicoes":["diabetes_tipo_1","dm1_com_hipertensao"]}'),
        ("pronto_atendimento", "Precisou de pronto atendimento?", "booleano", False, 68, None, '{"condicoes":["diabetes_tipo_1","dm1_com_hipertensao"]}'),
    ]

    for nome_campo, label, tipo_campo, obrigatorio, ordem, opcoes, regra_exibicao in campos:
        db.execute(
            text("""
                INSERT INTO campos_formulario
                (formulario_id, nome_campo, label, tipo_campo, obrigatorio, ordem, opcoes, regra_exibicao, ativo)
                SELECT
                :formulario_id, :nome_campo, :label, :tipo_campo, :obrigatorio, :ordem,
                CAST(:opcoes AS JSON), CAST(:regra_exibicao AS JSON), true
                WHERE NOT EXISTS (
                    SELECT 1 FROM campos_formulario
                    WHERE formulario_id = :formulario_id
                    AND nome_campo = :nome_campo
                )
            """),
            {
                "formulario_id": formulario_id,
                "nome_campo": nome_campo,
                "label": label,
                "tipo_campo": tipo_campo,
                "obrigatorio": obrigatorio,
                "ordem": ordem,
                "opcoes": opcoes,
                "regra_exibicao": regra_exibicao,
            }
        )

    db.commit()
    print("Seed dos módulos e formulário cardiometabólico criado com sucesso.")

except Exception as e:
    db.rollback()
    print(f"Erro ao executar seed: {e}")

finally:
    db.close()
