# Deploy e Publicação --- Integra Care

> **Versão:** 1.0.0\
> **Empresa:** Meyio DDS Digital\
> **Documento:** 04_DEPLOY.md\
> **Status:** Oficial

------------------------------------------------------------------------

# 1. Objetivo

Formalizar o processo oficial de publicação do Integra Care, garantindo
rastreabilidade, validação e segurança entre os ambientes.

# 2. Princípio Fundamental

> **Nenhuma alteração deve ser publicada diretamente em Produção.**

Fluxo obrigatório:

``` text
DEV
 ↓
HML
 ↓
Validação
 ↓
Produção
```

# 3. Componentes Publicados

O processo contempla três aplicações principais:

-   Backend
-   Portal Profissional
-   APP do Responsável

Cada componente possui seu próprio ciclo técnico de publicação, mas
todos devem permanecer funcionalmente compatíveis.

# 4. Estratégia de Branches

O fluxo oficial é:

``` text
Desenvolvimento local
        ↓
branch homolog
        ↓
HML
        ↓
Validação
        ↓
merge homolog → main
        ↓
Produção
```

A branch `main` representa o código oficial de Produção.

A branch `homolog` representa o código candidato à próxima publicação.

# 5. Ambientes Oficiais

## DEV

Utilizado para:

-   execução local;
-   desenvolvimento;
-   testes iniciais.

## HML

Utilizado para:

-   validação integrada;
-   testes funcionais;
-   conferência antes da publicação.

## Produção

Utilizado para:

-   operação oficial;
-   dados reais;
-   acesso dos usuários.

# 6. Fluxo do Backend

## DEV → HML

1.  Concluir o desenvolvimento.
2.  Validar localmente.
3.  Revisar as alterações.
4.  Registrar o commit.
5.  Publicar na branch `homolog`.
6.  Aguardar o deploy da HML.
7.  Validar API e Swagger.
8.  Validar banco e migrações, quando aplicável.

## HML → Produção

1.  Obter a validação da versão candidata.
2.  Confirmar a necessidade e a existência de backup.
3.  Revisar o estado das branches.
4.  Realizar o merge `homolog` → `main`.
5.  Acompanhar o deploy.
6.  Executar migrações, quando aplicável.
7.  Validar endpoints críticos.
8.  Registrar a publicação.

# 7. Fluxo do Portal Profissional

O Portal segue o ciclo:

1.  Desenvolvimento local.
2.  Testes em DEV.
3.  Publicação em HML.
4.  Validação das telas e dos fluxos.
5.  Merge para `main`.
6.  Deploy de Produção.
7.  Validação do domínio oficial.

Validações mínimas:

-   login;
-   navegação;
-   pacientes;
-   prontuário;
-   linhas de cuidado;
-   dashboards;
-   comunicação com a API.

# 8. Fluxo do APP do Responsável

O APP segue o mesmo princípio:

1.  Desenvolvimento local.
2.  Publicação em HML.
3.  Validação funcional.
4.  Merge para `main`.
5.  Publicação em Produção.
6.  Validação final.

Checklist mínimo:

-   login;
-   lista de pacientes;
-   seleção da linha de cuidado;
-   registro;
-   histórico;
-   comunicação com a API oficial.

# 9. Banco de Dados e Migrações

> **Código e estrutura do banco devem evoluir de forma coordenada.**

Antes de uma alteração estrutural em Produção:

1.  Revisar a migração.
2.  Testar em HML.
3.  Realizar backup.
4.  Confirmar explicitamente o ambiente.
5.  Aplicar a migração.
6.  Validar estrutura e dados.

> **Nunca execute uma migração em Produção sem confirmar explicitamente
> a conexão de destino.**

Operações sensíveis devem preservar:

-   rastreabilidade;
-   possibilidade de recuperação;
-   compatibilidade entre código e banco.

# 10. Checklist Pré-Deploy

Antes da publicação:

-   [ ] Alterações validadas em DEV
-   [ ] HML estável
-   [ ] Testes concluídos
-   [ ] Branches revisadas
-   [ ] Variáveis de ambiente verificadas
-   [ ] CORS revisado, quando aplicável
-   [ ] Migrações testadas
-   [ ] Backup realizado, quando necessário
-   [ ] Plano de rollback conhecido

# 11. Checklist Pós-Deploy

## Backend

-   [ ] API respondendo
-   [ ] Swagger acessível
-   [ ] Autenticação funcionando
-   [ ] Endpoints críticos validados

## Portal Profissional

-   [ ] Login funcionando
-   [ ] Navegação validada
-   [ ] Pacientes acessíveis
-   [ ] Prontuário funcionando
-   [ ] Linhas de cuidado acessíveis
-   [ ] Dashboards funcionando

## APP do Responsável

-   [ ] Login funcionando
-   [ ] Pacientes acessíveis
-   [ ] Registro funcionando
-   [ ] Histórico funcionando

# 12. Rollback

Se houver falha relevante:

1.  Interromper novas alterações.
2.  Identificar o componente afetado.
3.  Avaliar código e banco separadamente.
4.  Restaurar a versão estável do código, quando necessário.
5.  Restaurar backup do banco somente quando necessário e tecnicamente
    justificado.
6.  Validar a recuperação.
7.  Registrar o incidente e as ações realizadas.

> **Rollback de código e rollback de banco são operações diferentes e
> devem ser avaliadas separadamente.**

Uma reversão de código não implica automaticamente reversão do banco.

Da mesma forma, a restauração de um banco deve ser tratada como operação
sensível e executada somente após avaliação do impacto.

# 13. Domínios Oficiais

## Produção

-   Portal Profissional: `https://care.meyio.com.br`
-   APP do Responsável: `https://app.care.meyio.com.br`
-   API: `https://api.care.meyio.com.br`

Os domínios antigos não fazem parte do fluxo operacional oficial.

# 14. Registro da Release

Após uma publicação bem-sucedida:

-   atualizar o `CHANGELOG.md`;
-   atualizar o `13_RELEASES.md`, quando houver nova versão;
-   atualizar o `MILESTONES.md`;
-   criar tag Git, quando aplicável;
-   atualizar a documentação afetada.

# 15. Responsabilidade e Governança

Um deploy não termina quando o serviço aparece apenas como disponível.

Ele termina quando:

> **O código foi publicado, o banco foi validado, os fluxos críticos
> foram testados e a documentação foi atualizada.**

Toda publicação deve preservar:

-   estabilidade;
-   rastreabilidade;
-   segurança;
-   documentação;
-   capacidade de recuperação.

# 16. Fluxo Oficial Resumido

``` text
Desenvolver
   ↓
Testar em DEV
   ↓
Publicar em HML
   ↓
Validar
   ↓
Realizar Backup
   ↓
Merge homolog → main
   ↓
Publicar em Produção
   ↓
Validar Produção
   ↓
Documentar a Release
```

# 17. Considerações Finais

O processo oficial de deploy protege a estabilidade do Integra Care e
reduz o risco de alterações não validadas em Produção.

A disciplina entre ambientes é obrigatória:

**DEV → HML → Validação → Produção**

Nenhuma urgência operacional deve eliminar as etapas essenciais de
validação, segurança e rastreabilidade.

------------------------------------------------------------------------

**© Meyio DDS Digital**

**Integra Care --- Plataforma Modular de Gestão Longitudinal de Linhas
de Cuidado**
