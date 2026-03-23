#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
EMAIL="${ADMIN_EMAIL:-admin@sentinela.com}"
SENHA="${ADMIN_SENHA:-Senha@123}"

TOKEN=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=${EMAIL}&password=${SENHA}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "1) /me (200 esperado)"
curl -s -o /dev/null -w "HTTP=%{http_code}\n" "$BASE_URL/me" -H "Authorization: Bearer $TOKEN"

echo "2) POST /pacientes/ sem token (401 esperado)"
curl -s -o /dev/null -w "HTTP=%{http_code}\n" -X POST "$BASE_URL/pacientes/" \
  -H "Content-Type: application/json" \
  -d '{"nome":"Sem token"}'

echo "3) POST /pacientes/ com token (200/201 esperado)"
curl -s -o /dev/null -w "HTTP=%{http_code}\n" -X POST "$BASE_URL/pacientes/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"nome":"Smoke Patient","data_nascimento":"2018-05-10","genero":"M","responsavel_nome":"Maria","responsavel_email":"maria@email.com"}'

echo "4) GET /pacientes/ com token (200 esperado)"
curl -s -o /dev/null -w "HTTP=%{http_code}\n" "$BASE_URL/pacientes/" -H "Authorization: Bearer $TOKEN"

echo "SMOKE: OK ✅"
