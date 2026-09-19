-- One-time, explicitly approved HML inventory only. Never invoked by the app
-- or Alembic. Run only at 8c01a0d1a000, with all writers stopped and backup.
BEGIN;
LOCK TABLE diagnosticos, intervencoes, intervencoes_cardiometabolicas,
    paciente_modulos, whatsapp_conversas, modulos_clinicos IN EXCLUSIVE MODE;
DO $$
BEGIN
    IF (SELECT version_num FROM alembic_version) IS DISTINCT FROM '8c01a0d1a000' THEN
        RAISE EXCEPTION 'Wrong revision; remediation aborted';
    END IF;
    IF (SELECT count(*) FROM modulos_clinicos WHERE ativo IS TRUE AND
        ((id=1 AND slug='neurodesenvolvimento') OR (id=2 AND slug='cardiometabolico'))) <> 2 THEN
        RAISE EXCEPTION 'Canonical modules changed';
    END IF;
    IF (SELECT array_agg(id ORDER BY id) FROM diagnosticos) IS DISTINCT FROM ARRAY[1,2,3,4,5]
       OR EXISTS (SELECT 1 FROM diagnosticos WHERE modulo_id IS NOT NULL) THEN
        RAISE EXCEPTION 'Diagnosis inventory changed';
    END IF;
    IF (SELECT array_agg(id ORDER BY id) FROM intervencoes) IS DISTINCT FROM
        ARRAY[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16]
       OR EXISTS (SELECT 1 FROM intervencoes WHERE modulo_id IS NOT NULL) THEN
        RAISE EXCEPTION 'Intervention inventory changed';
    END IF;
    IF EXISTS (
        SELECT 1 FROM (SELECT paciente_id FROM diagnosticos UNION SELECT paciente_id FROM intervencoes) p
        WHERE NOT EXISTS (SELECT 1 FROM paciente_modulos m WHERE m.paciente_id=p.paciente_id AND m.modulo_id=1 AND m.ativo IS TRUE)
           OR EXISTS (SELECT 1 FROM paciente_modulos m WHERE m.paciente_id=p.paciente_id AND m.modulo_id<>1 AND m.ativo IS TRUE)
    ) THEN
        RAISE EXCEPTION 'Inventoried membership changed; no inference allowed';
    END IF;
    IF (SELECT count(*) FROM intervencoes_cardiometabolicas) <> 2 OR
       (SELECT count(*) FROM intervencoes_cardiometabolicas WHERE (id=1 AND paciente_id=6) OR (id=2 AND paciente_id=7)) <> 2 THEN
        RAISE EXCEPTION 'Specialized inventory changed';
    END IF;
    IF EXISTS (SELECT 1 FROM paciente_modulos WHERE paciente_id=6 AND modulo_id=2)
       OR NOT EXISTS (SELECT 1 FROM paciente_modulos WHERE paciente_id=6 AND modulo_id=1 AND ativo IS TRUE)
       OR (SELECT count(DISTINCT modulo_id) FROM paciente_modulos WHERE paciente_id=7 AND modulo_id IN (1,2) AND ativo IS TRUE) <> 2 THEN
        RAISE EXCEPTION 'Patient 6/7 membership changed';
    END IF;
    IF (SELECT count(*) FROM whatsapp_conversas) <> 1 OR
       (SELECT count(*) FROM whatsapp_conversas WHERE id=1 AND responsavel_id=3
        AND paciente_id IS NULL AND etapa_atual='INICIO' AND data_referencia IS NULL
        AND respostas_json::jsonb='{}'::jsonb) <> 1 THEN
        RAISE EXCEPTION 'Conversation changed; human review required';
    END IF;

    UPDATE diagnosticos SET modulo_id=1 WHERE id IN (1,2,3,4,5);
    UPDATE intervencoes SET modulo_id=1 WHERE id BETWEEN 1 AND 16;
    INSERT INTO paciente_modulos (paciente_id,modulo_id,ativo,data_inicio,data_fim,observacao)
    VALUES (6,2,TRUE,DATE '2026-06-09',NULL,
        'Saneamento aprovado da massa HML: primeira evidência Cardio disponível em 2026-06-09; não afirma início histórico absoluto do acompanhamento.');
    DELETE FROM whatsapp_conversas WHERE id=1 AND responsavel_id=3
        AND paciente_id IS NULL AND etapa_atual='INICIO' AND data_referencia IS NULL
        AND respostas_json::jsonb='{}'::jsonb;
END $$;
COMMIT;
