# Integra Care — Checklist Sprint 2.9

## Objetivo

Implementar o Motor Universal de Avaliações Clínicas, iniciando por M-CHAT e preparando a arquitetura para Denver, CARS, VB-MAPP e demais instrumentos.

## Status atual

- Clinical Engine Neuro concluído na Sprint 2.8.
- Motor universal criado em `app/services/clinical_engine`.
- MChatEngine implementado e validado via shell.
- AssessmentContext criado.
- AssessmentService criado.
- AssessmentRunner criado.

## Próximos passos

1. Criar tabela `avaliacoes_clinicas`.
2. Criar model SQLAlchemy.
3. Criar schema Pydantic.
4. Criar service de persistência.
5. Criar endpoint genérico de execução.
6. Persistir resultado do M-CHAT.
7. Criar DenverEngine inicial.
8. Integrar avaliações ao prontuário.
9. Integrar avaliações à timeline.
10. Validar em HML antes de produção.

## Regra de deploy

- Desenvolvimento local primeiro.
- Commit pequeno por etapa.
- Deploy em homologação antes de produção.
- Produção somente após validação funcional no HML.