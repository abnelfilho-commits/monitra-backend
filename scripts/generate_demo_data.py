import random
from datetime import datetime, timedelta
import requests

API = "http://localhost:8000"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZXhwIjoxNzczNzc5Nzg4fQ.XG95HTEFkYMVxmrOxI7It8NGG7kLdtcGhjoe5EAjxCQ"

headers = {"Authorization": f"Bearer {TOKEN}"}

nomes = [
    "Lucas", "Rafael", "Pedro", "Ana", "Maria", "João", "Arthur", "Isabella",
    "Helena", "Enzo", "Miguel", "Valentina", "Laura", "Davi", "Theo",
    "Matheus", "Lívia", "Gabriel", "Beatriz", "Sophia"
]

sobrenomes = [
    "Silva", "Souza", "Costa", "Oliveira", "Pereira",
    "Almeida", "Ferreira", "Rodrigues", "Gomes", "Martins"
]

tipos_intervencao = [
    "Ajuste terapêutico",
    "Orientação familiar",
    "Reavaliação clínica",
    "Intervenção comportamental",
    "Acompanhamento multiprofissional",
    "Plano de rotina",
]

descricoes_intervencao = [
    "Reforçada rotina estruturada para redução de irritabilidade.",
    "Orientação aos responsáveis sobre manejo de crise sensorial.",
    "Ajustados estímulos ambientais e rotina de sono.",
    "Revisado plano terapêutico com foco em autorregulação.",
    "Alinhamento multiprofissional para acompanhamento longitudinal.",
    "Definidas estratégias de suporte comportamental em casa.",
]


def nome_random():
    return f"{random.choice(nomes)} {random.choice(sobrenomes)}"


def criar_paciente(nome):
    payload = {
        "nome": nome,
        "data_nascimento": "2019-06-10",
        "genero": random.choice(["M", "F"]),
        "responsavel_nome": "Responsável",
        "responsavel_email": "responsavel@email.com",
        "profissional_id": 1,
    }

    r = requests.post(f"{API}/pacientes/", json=payload, headers=headers, timeout=30)

    if r.status_code >= 400:
        print("ERRO PACIENTE:", r.status_code, r.text)

    r.raise_for_status()
    return r.json()["id"]


def criar_registro(paciente_id, data, perfil):
    if perfil == "melhorando":
        sono = random.choice([3, 4, 5, 4, 5])
        irrit = random.choice([0, 1, 1, 2])
        crise = random.choice([0, 0, 1])

    elif perfil == "piorando":
        sono = random.choice([1, 2, 2])
        irrit = random.choice([2, 3, 4, 3])
        crise = random.choice([1, 2, 3, 2])

    elif perfil == "critico":
        sono = random.choice([1, 1, 2])
        irrit = random.choice([3, 4, 4])
        crise = random.choice([2, 3, 3])

    else:  # estavel
        sono = random.choice([2, 3, 4])
        irrit = random.choice([1, 2, 2])
        crise = random.choice([1, 1, 2])

    payload = {
        "paciente_id": paciente_id,
        "data": data,
        "sono_qualidade": sono,
        "evacuacao": random.choice([True, False]),
        "consistencia_fezes": random.randint(2, 6),
        "irritabilidade": irrit,
        "crise_sensorial": crise,
        "observacao": "Registro clínico gerado automaticamente para demonstração",
    }

    r = requests.post(f"{API}/registros/", json=payload, headers=headers, timeout=30)

    if r.status_code >= 400:
        print("ERRO REGISTRO:", r.status_code, r.text)

    r.raise_for_status()


def criar_intervencao(paciente_id, dias_atras):
    data_intervencao = (
        datetime.now() - timedelta(days=dias_atras, hours=random.randint(8, 17))
    ).isoformat()

    payload = {
        "paciente_id": paciente_id,
        "profissional_id": 1,
        "tipo": random.choice(tipos_intervencao),
        "descricao": random.choice(descricoes_intervencao),
        "data_intervencao": data_intervencao,
    }

    r = requests.post(f"{API}/intervencoes/", json=payload, headers=headers, timeout=30)

    if r.status_code >= 400:
        print("ERRO INTERVENCAO:", r.status_code, r.text)

    r.raise_for_status()


print("Gerando pacientes...")

total_pacientes = 120

perfis = (
    ["melhorando"] * 40
    + ["estavel"] * 30
    + ["piorando"] * 30
    + ["critico"] * 10
    + ["sem_dados"] * 10
)

random.shuffle(perfis)

for i in range(total_pacientes):
    nome = f"{nome_random()} {i}"
    paciente_id = criar_paciente(nome)
    perfil = perfis[i]

    if perfil != "sem_dados":
        for d in range(30):
            data = (datetime.now() - timedelta(days=d)).date().isoformat()
            criar_registro(paciente_id, data, perfil)

    # gerar intervenções por perfil
    qtd_intervencoes = 0
    if perfil == "critico":
        qtd_intervencoes = random.randint(4, 6)
    elif perfil == "piorando":
        qtd_intervencoes = random.randint(2, 4)
    elif perfil == "estavel":
        qtd_intervencoes = random.randint(1, 2)
    elif perfil == "melhorando":
        qtd_intervencoes = random.randint(1, 3)

    for _ in range(qtd_intervencoes):
        criar_intervencao(paciente_id, dias_atras=random.randint(1, 30))

print("Base clínica gerada com sucesso.")
