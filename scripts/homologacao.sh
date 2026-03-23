#!/usr/bin/env bash
set -euo pipefail

BASE="http://127.0.0.1:8000"

require() { command -v "$1" >/dev/null 2>&1 || { echo "Falta instalar: $1"; exit 1; }; }
require jq
require curl

assert_code() {
  local got="$1"
  local expected="$2"
  local label="$3"
  if [[ "$got" != "$expected" ]]; then
    echo "❌ FAIL: $label (esperado HTTP $expected, obtido HTTP $got)"
    exit 1
  fi
  echo "✅ OK: $label (HTTP $got)"
}

echo "== 1) Criar clínica"
CLINICA_RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/clinicas/" \
  -H "Content-Type: application/json" \
  -d '{"nome":"Clinica Homolog","cnpj":"12.345.678/0001-99"}')

CLINICA_BODY=$(echo "$CLINICA_RESP" | head -n 1)
CLINICA_CODE=$(echo "$CLINICA_RESP" | tail -n 1)

# seu backend retorna 200 aqui (ok)
assert_code "$CLINICA_CODE" "200" "POST /clinicas/"
CLINICA_ID=$(echo "$CLINICA_BODY" | jq -r '.id')
[[ "$CLINICA_ID" != "null" && -n "$CLINICA_ID" ]] || { echo "❌ FAIL: clinica_id vazio"; exit 1; }

echo "== 2) Criar usuário"
EMAIL="homolog_$(date +%s)@sentinela.com"
USER_RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/usuarios/" \
  -H "Content-Type: application/json" \
  -d "{\"nome\":\"Usuario Homolog\",\"email\":\"$EMAIL\",\"senha\":\"Senha@123\",\"perfil\":\"PROFISSIONAL\",\"clinica_id\":$CLINICA_ID}")

USER_BODY=$(echo "$USER_RESP" | head -n 1)
USER_CODE=$(echo "$USER_RESP" | tail -n 1)

assert_code "$USER_CODE" "201" "POST /usuarios/"
USER_ID=$(echo "$USER_BODY" | jq -r '.id')
[[ "$USER_ID" != "null" && -n "$USER_ID" ]] || { echo "❌ FAIL: user_id vazio"; exit 1; }

echo "== 3) Criar paciente"
PAC_RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/pacientes/" \
  -H "Content-Type: application/json" \
  -d "{\"nome\":\"Paciente Homolog\",\"clinica_id\":$CLINICA_ID,\"data_nascimento\":\"2018-05-10\"}")

PAC_BODY=$(echo "$PAC_RESP" | head -n 1)
PAC_CODE=$(echo "$PAC_RESP" | tail -n 1)

# seu backend retorna 200 aqui (ok)
assert_code "$PAC_CODE" "200" "POST /pacientes/"
PAC_ID=$(echo "$PAC_BODY" | jq -r '.id')
[[ "$PAC_ID" != "null" && -n "$PAC_ID" ]] || { echo "❌ FAIL: paciente_id vazio"; exit 1; }

echo "== 4) Vincular profissional -> paciente"
VINC_RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/vinculos/profissional-paciente" \
  -H "Content-Type: application/json" \
  -d "{\"profissional_id\":$USER_ID,\"paciente_id\":$PAC_ID}")

VINC_BODY=$(echo "$VINC_RESP" | head -n 1)
VINC_CODE=$(echo "$VINC_RESP" | tail -n 1)

assert_code "$VINC_CODE" "200" "POST /vinculos/profissional-paciente"

echo "== 5) Criar registro diário"
HOJE="$(date +%F)"
REG_RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/registros/" \
  -H "Content-Type: application/json" \
  -d "{\"paciente_id\":$PAC_ID,\"data\":\"$HOJE\",\"evacuacao\":true,\"crise_sensorial\":false,\"observacao\":\"ok\"}")

REG_BODY=$(echo "$REG_RESP" | head -n 1)
REG_CODE=$(echo "$REG_RESP" | tail -n 1)

assert_code "$REG_CODE" "201" "POST /registros/"

echo "== 6) Registro duplicado (espera 409)"
REG2_RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/registros/" \
  -H "Content-Type: application/json" \
  -d "{\"paciente_id\":$PAC_ID,\"data\":\"$HOJE\"}")

REG2_CODE=$(echo "$REG2_RESP" | tail -n 1)
assert_code "$REG2_CODE" "409" "POST /registros/ (duplicado)"

echo "== 7) Listar registros do paciente"
LIST_REG_RESP=$(curl -s -w "\n%{http_code}" "$BASE/registros/paciente/$PAC_ID")
LIST_REG_BODY=$(echo "$LIST_REG_RESP" | head -n 1)
LIST_REG_CODE=$(echo "$LIST_REG_RESP" | tail -n 1)

assert_code "$LIST_REG_CODE" "200" "GET /registros/paciente/{id}"
echo "$LIST_REG_BODY" | jq -e 'type=="array" and length>=1' >/dev/null || { echo "❌ FAIL: lista de registros vazia"; exit 1; }

echo "== 8) Criar intervenção"
INT_RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/intervencoes/" \
  -H "Content-Type: application/json" \
  -d "{\"paciente_id\":$PAC_ID,\"profissional_id\":$USER_ID,\"tipo\":\"fonoaudiologia\",\"descricao\":\"Sessao 1\",\"data_intervencao\":\"$HOJE\"T10:00:00\"}")

INT_CODE=$(echo "$INT_RESP" | tail -n 1)
# seu backend retorna 200 aqui (ok)
assert_code "$INT_CODE" "200" "POST /intervencoes/"

echo "== 9) Timeline do paciente"
TL_RESP=$(curl -s -w "\n%{http_code}" "$BASE/pacientes/$PAC_ID/timeline")
TL_CODE=$(echo "$TL_RESP" | tail -n 1)
assert_code "$TL_CODE" "200" "GET /pacientes/{id}/timeline"

echo
echo "🎉 HOMOLOGAÇÃO PASSOU"
echo "Clínica=$CLINICA_ID | Usuário=$USER_ID | Paciente=$PAC_ID | Data=$HOJE"

