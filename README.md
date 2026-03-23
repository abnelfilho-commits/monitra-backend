# Sentinela Backend (FastAPI + Postgres + JWT + Docker)

Backend do projeto Sentinela (MVP técnico), executando em ambiente local com Docker Compose.

## Stack
- FastAPI
- SQLAlchemy
- Postgres (Docker)
- JWT (python-jose)
- Hash de senha: **pbkdf2_sha256** (passlib)

---

## Pré-requisitos
- Docker
- Docker Compose

> Não é necessário ativar `venv` para rodar via Docker.

---

## Estrutura (resumo)
- `app/main.py` → inicializa FastAPI e registra routers
- `app/database.py` → engine/session/Base
- `app/core/security.py` → hash/verificação de senha + JWT encode/decode
- `app/core/deps.py` → dependency `get_usuario_atual` (Bearer token)
- `app/scripts/bootstrap_db.py` → cria tabelas (`create_all`)
- `app/scripts/seed_admin.py` → cria admin idempotente
- `scripts/smoke_backend.sh` → smoke test do backend

---

## Variáveis de ambiente (.env)
Crie um arquivo `.env` na raiz (mesmo nível do `docker-compose.yml`):

```env
# Postgres (Docker)
POSTGRES_DB=sentinela
POSTGRES_USER=sentinela
POSTGRES_PASSWORD=sentinela

# URL correta para dentro do container
DATABASE_URL=postgresql+psycopg2://sentinela:sentinela@db:5432/sentinela

# JWT
SECRET_KEY=coloque_uma_chave_grande_e_aleatoria_aqui
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Seed automático
ADMIN_EMAIL=admin@sentinela.com
ADMIN_SENHA=Senha@123
ADMIN_NOME=Admin Sistema
ADMIN_PERFIL=ADMIN_CLINICA
