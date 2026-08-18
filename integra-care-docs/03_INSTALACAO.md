# Instalação e Ambiente Local --- Integra Care

> **Versão:** 1.0.0\
> **Empresa:** Meyio DDS Digital\
> **Documento:** 03_INSTALACAO.md\
> **Status:** Oficial

------------------------------------------------------------------------

# 1. Objetivo

Orientar a preparação e a execução do ambiente local de desenvolvimento
do Integra Care.

Este documento cobre a instalação e a inicialização dos componentes
necessários para desenvolvimento e testes locais.

O processo de publicação em Homologação e Produção é tratado
exclusivamente no `04_DEPLOY.md`.

# 2. Escopo

O ambiente local é composto por três aplicações principais:

-   Backend
-   Portal Profissional
-   APP do Responsável

Arquitetura local:

``` text
Portal Profissional ─┐
                     ├──► API FastAPI ──► PostgreSQL
APP do Responsável ──┘
```

# 3. Pré-requisitos

Antes de iniciar, verifique a disponibilidade das seguintes ferramentas:

-   Git
-   Python
-   Node.js
-   npm
-   Docker
-   Docker Compose
-   PostgreSQL
-   Editor de código
-   Acesso autorizado aos repositórios do projeto

As versões utilizadas deverão ser compatíveis com as configurações
vigentes nos respectivos repositórios.

# 4. Preparação do Backend

O fluxo padrão de preparação do Backend é:

1.  Clonar ou atualizar o repositório autorizado.
2.  Acessar o diretório do projeto.
3.  Criar um ambiente virtual Python.
4.  Ativar o ambiente virtual.
5.  Instalar as dependências.
6.  Configurar as variáveis de ambiente locais.
7.  Inicializar a infraestrutura necessária.
8.  Executar as migrações do banco.
9.  Iniciar a API.
10. Validar o Swagger.

Exemplo genérico:

``` text
git clone <REPOSITORIO_AUTORIZADO>
cd <DIRETORIO_BACKEND>

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

> Os nomes exatos de repositórios, diretórios e comandos adicionais
> deverão seguir a configuração oficial vigente do projeto.

# 5. Banco de Dados Local

O ambiente de desenvolvimento utiliza PostgreSQL.

Preferencialmente, a infraestrutura local deve ser executada de forma
isolada por meio de Docker.

Etapas:

1.  Inicializar o banco local.
2.  Confirmar a configuração da `DATABASE_URL`.
3.  Validar a conexão.
4.  Executar as migrações Alembic.
5.  Confirmar a versão estrutural do banco.

Exemplo genérico:

``` text
alembic upgrade head
```

## Regra de Segurança

> **O ambiente DEV local nunca deve apontar para os bancos de
> Homologação ou Produção.**

Antes de executar migrações, scripts de carga, restaurações ou operações
sensíveis, confirme sempre qual banco está configurado.

# 6. Inicialização da API

Após preparar o banco e executar as migrações:

1.  Ative o ambiente virtual.
2.  Confirme as variáveis de ambiente.
3.  Inicie a aplicação FastAPI.
4.  Valide a resposta da API.
5.  Acesse a documentação Swagger local.

O comando exato de inicialização deverá seguir a configuração oficial do
Backend.

# 7. Portal Profissional

Fluxo padrão:

1.  Clonar ou atualizar o repositório.
2.  Acessar o diretório do Portal.
3.  Instalar as dependências.
4.  Configurar a URL da API local.
5.  Iniciar o servidor de desenvolvimento.
6.  Validar login e navegação.

Exemplo genérico:

``` text
npm install
npm run dev
```

O Portal deve estar configurado para consumir a API do ambiente local
durante o desenvolvimento.

# 8. APP do Responsável

O APP segue o mesmo princípio de preparação do Portal:

1.  Clonar ou atualizar o repositório.
2.  Instalar as dependências.
3.  Configurar as variáveis de ambiente.
4.  Apontar para a API local.
5.  Iniciar o servidor de desenvolvimento.
6.  Validar o fluxo principal.

Validações mínimas:

-   Login
-   Lista de pacientes
-   Seleção da linha de cuidado
-   Registro
-   Histórico

# 9. Variáveis de Ambiente

As variáveis de ambiente devem ser configuradas conforme cada aplicação.

Exemplos de nomes utilizados na plataforma:

``` text
DATABASE_URL
SECRET_KEY
ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES
VITE_API_URL
```

A documentação oficial deverá registrar apenas:

-   nome da variável;
-   finalidade;
-   aplicação que a utiliza.

Nunca devem ser incluídos:

-   senhas reais;
-   tokens;
-   chaves privadas;
-   credenciais de banco;
-   segredos de Produção.

> **Credenciais, tokens, senhas e chaves privadas nunca devem ser
> versionados no repositório.**

Arquivos `.env` devem permanecer protegidos e fora do controle de
versão.

# 10. Inicialização Diária

A sequência recomendada para iniciar o ambiente de desenvolvimento é:

``` text
1. Banco de Dados / Docker
2. Backend
3. Portal Profissional
4. APP do Responsável, quando necessário
```

Essa ordem facilita a identificação de problemas de dependência e
comunicação entre os componentes.

# 11. Validação do Ambiente

Antes de iniciar uma atividade de desenvolvimento, confirme:

-   [ ] Banco local disponível
-   [ ] Variáveis de ambiente corretas
-   [ ] Migrações atualizadas
-   [ ] API respondendo
-   [ ] Swagger acessível
-   [ ] Portal Profissional abrindo
-   [ ] APP do Responsável abrindo, quando necessário
-   [ ] Login funcionando
-   [ ] Comunicação com a API local confirmada

# 12. Problemas Comuns

## Porta ocupada

Verifique se outro processo está utilizando a porta necessária para o
serviço.

## Ambiente virtual não ativado

Confirme se o `venv` está ativo antes de executar comandos Python.

## Dependência ausente

Atualize as dependências conforme o arquivo oficial do projeto.

## Banco indisponível

Verifique o container, a conexão e a configuração da `DATABASE_URL`.

## Migração pendente

Confirme o estado do Alembic e aplique as migrações necessárias no banco
local.

## Variável de ambiente incorreta

Revise o arquivo de configuração local e confirme o ambiente de destino.

## Frontend apontando para API errada

Confirme a variável responsável pela URL da API antes de iniciar os
testes.

# 13. Segurança do Ambiente Local

As seguintes regras são obrigatórias:

-   Nunca utilizar o banco de Produção para desenvolvimento.
-   Nunca utilizar o banco de Homologação como banco local.
-   Nunca registrar segredos na documentação.
-   Nunca versionar arquivos `.env`.
-   Confirmar o ambiente antes de executar migrações.
-   Realizar backup antes de operações sensíveis.
-   Utilizar somente acessos autorizados aos repositórios e serviços.

# 14. Limites deste Documento

O `03_INSTALACAO.md` explica:

> **Como preparar e executar o ambiente DEV local.**

O `04_DEPLOY.md` explica:

> **Como promover alterações de DEV para HML, validar e publicar em
> Produção.**

Essa separação preserva a clareza entre desenvolvimento local e operação
dos ambientes oficiais.

# 15. Considerações Finais

Um ambiente local corretamente isolado é essencial para preservar a
segurança e a estabilidade do Integra Care.

Toda atividade de desenvolvimento deve ocorrer em DEV, seguir para
Homologação e somente alcançar Produção após validação formal.

Fluxo oficial:

**DEV → HML → Validação → Produção**

------------------------------------------------------------------------

**© Meyio DDS Digital**

**Integra Care --- Plataforma Modular de Gestão Longitudinal de Linhas
de Cuidado**
