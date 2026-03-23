#!/usr/bin/env bash
set -euo pipefail

BASE="http://127.0.0.1:8000"

require() { command -v "$1" >/dev/null 2>&1 || { echo "Falta instalar: $1"; exit 1; }; }
require jq
require curl

ADMIN_EMAIL="${ADMIN_EMAIL:-admin@sentinela.com}"
ADMIN_SENHA="${ADMIN_SENHA:-Senha@123}"

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

echo "== 0) Teste negativo (sem token deve dar 401)"
NEG=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/pacientes/")
assert_code "$NEG" "401" "GET /pacientes/ sem token"

echo "== 1) Login (OAuth2 form)"
LOGIN_RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=$ADMIN_EMAIL&password=$ADMIN_SENHA")

LOGIN_BODY=$(echo "$LOGIN_RESP" | head -n 1)
LOGIN_CODE=$(echo "$LOGIN_RESP" | tail -n 1)

assert_code "$LOGIN_CODE" "200" "POST /auth/login"

TOKEN=$(echo "$LOGIN_BODY" | jq -r '.access_token')
[[ -n "$TOKEN" && "$TOKEN" != "null" ]] || { echo "❌ FAIL: token vazio"; exit 1; }

AUTH=(-H "Authorization: Bearer $TOKEN")

echo "== 2) Criar clínica"
CLINICA_RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/clinicas/" \
  "${AUTH[@]}" \
  -H "Content-Type: application/json" \
  -d '{"nome":"Clinica Homolog JWT","cnpj":"12.345.678/0001-99"}')

CLINICA_BODY=$(echo "$CLINICA_RESP" | head -n 1)
CLINICA_CODE=$(echo "$CLINICA_RESP" | tail -n 1)

assert_code "$CLINICA_CODE" "200" "POST /clinicas/"
CLINICA_ID=$(echo "$CLINICA_BODY" | jq -r '.id')

echo "== 3) Criar usuário"
EMAIL="homolog_$(date +%s)@sentinela.com"
USER_RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/usuarios/" \
  "${AUTH[@]}" \
  -H "Content-Type: application/json" \
  -d "{\"nome\":\"Usuario Homolog\",\"email\":\"$EMAIL\",\"senha\":\"Senha@123\",\"perfil\":\"PROFISSIONAL\",\"clinica_id\":$CLINICA_ID}")

USER_BODY=$(echo "$USER_RESP" | head -n 1)
USER_CODE=$(echo "$USER_RESP" | tail -n 1)

assert_code "$USER_CODE" "201" "POST /usuarios/"
USER_ID=$(echo "$USER_BODY" | jq -r '.id')

echo "== 4) Criar paciente"
PAC_RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/pacientes/" \
  "${AUTH[@]}" \
  -H "Content-Type: application/json" \
  -d "{\"nome\":\"Paciente Homolog\",\"clinica_id\":$CLINICA_ID,\"data_nascimento\":\"2018-05-10\"}")

PAC_BODY=$(echo "$PAC_RESP" | head -n 1)
PAC_CODE=$(echo "$PAC_RESP" | tail -n 1)

assert_code "$PAC_CODE" "200" "POST /pacientes/"
PAC_ID=$(echo "$PAC_BODY" | jq -r '.id')

echo "== 5) Vincular profissional"
VINC_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/vinculos/profissional-paciente" \
  "${AUTH[@]}" \
  -H "Content-Type: application/json" \
  -d "{\"profissional_id\":$USER_ID,\"paciente_id\":$PAC_ID}")

assert_code "$VINC_CODE" "200" "POST /vinculos/profissional-paciente"

echo "== 6) Criar registro"
HOJE="$(date +%F)"
REG_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/registros/" \
  "${AUTH[@]}" \
  -H "Content-Type: application/json" \
  -d "{\"paciente_id\":$PAC_ID,\"data\":\"$HOJE\"}")

assert_code "$REG_CODE" "201" "POST /registros/"

echo "== 7) Registro duplicado (esperado 409)"
REG2_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/registros/" \
  "${AUTH[@]}" \
  -H "Content-Type: application/json" \
  -d "{\"paciente_id\":$PAC_ID,\"data\":\"$HOJE\"}")

assert_code "$REG2_CODE" "409" "POST /registros/ duplicado"

echo "== 8) Timeline"
TL_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  "$BASE/pacientes/$PAC_ID/timeline" "${AUTH[@]}")

assert_code "$TL_CODE" "200" "GET /pacientes/{id}/timeline"

echo
echo "🎉 HOMOLOGAÇÃO JWT COMPLETA E APROVADA"

