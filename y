# Postgres (Docker)
POSTGRES_DB=sentinela
POSTGRES_USER=sentinela
POSTGRES_PASSWORD=sentinela123

# URL correta para dentro do container
DATABASE_URL=postgresql+psycopg2://sentinela:sentinela123@db:5432/sentinela

# JWT
SECRET_KEY=coloque_uma_chave_grande_e_aleatoria_aqui
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Seed automático
ADMIN_EMAIL=admin@neurovida.local
ADMIN_NOME=Admin NeuroVida
ADMIN_SENHA=Senha@123
ADMIN_FORCE_RESET_PASSWORD=false
DEFAULT_CLINICA_NOME=Clínica NeuroVida
DEFAULT_CLINICA_EMAIL=contato@neurovida.local
