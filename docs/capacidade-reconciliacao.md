# Reconciliação canônica de capacidades

Revision: `capacidade_reconciliacao_v1`, filha direta de `w2b_checkin_v1`.
As migrations anteriores e a configuração histórica permanecem intactas.

## Contrato e entradas

A tabela congelada possui oito colunas, ID integer SERIAL com sequence própria,
FK RESTRICT para profissional_instituicoes, minutos positivos, período fechado
inclusivo e exclusão GiST de sobreposição por profissional_instituicao_id somente
para registros ativos. Não possui triggers, RLS, policies, rules ou views dependentes.
A proveniência institucional mantém quatro alvos mutuamente exclusivos e os seis
pares explícitos de operação/resultado LINK e CAPACITY. Não há índice adicional
sobre institucional_operacoes.capacidade_profissional_id.

A migration aceita somente:

- CANONICAL_WITHOUT_CAPACITY: contrato G2B1 de proveniência intacto, sem tabela,
  sequence ou índices residuais de capacidade; cria o contrato congelado.
- LEGACY_I1_EXACT_CAPACITY: catálogo integral equivalente, incluindo nomes
  operacionais explícitos, tipos, ordem, defaults, nullability, PK/FK/CHECK/EXCLUDE,
  índices válidos/prontos, sequence/ownership e ausência de mecanismos adicionais;
  valida e adota sem DDL de recriação ou alteração de dados.

Qualquer terceiro estado aborta. Representações de casts textuais inseridos pelo
PostgreSQL são normalizadas; expressões booleanas desconhecidas não são aceitas.
Os nomes não especificados dos CHECKs simples/FK de capacidade são comparados
por suas definições, sem inferir equivalência pela presença da tabela.

A execução exige PostgreSQL 18+, READ COMMITTED e btree_gist preexistente. Locks
ACCESS EXCLUSIVE sobre proveniência e vínculo profissional (e capacidade, se
presente) estabilizam o catálogo e as escritas até o término da transação do
chamador. O executor operacional futuro deve impor timeouts e janela apropriada.
Não há commit interno, backfill, criação de acesso ou API de capacidades.

## Downgrade e adoção HML

Downgrade é sempre bloqueado, inclusive vazio: o marcador não registra se os
objetos foram criados ou adotados, e sua remoção automática poderia apagar
histórico anterior à revision. Recovery exige decisão operacional própria.

O procedimento excepcional de adoção do marcador HML permanece separado e NÃO
é implementado aqui. Não há suporte para executar upgrade diretamente de um
marcador órfão. A simulação local começa com marcador canônico F1 e extensão I1
construída por fixture independente, e percorre W1A até o novo head.
Nenhuma autorização de mutação HML decorre dos testes locais.

## Validação local

Testes em PostgreSQL 18 descartável cobrem bootstrap vazio, evolução de W2B,
adoção I1 desde F1 com dados sintéticos, preservação de IDs/OIDs/sequence e histórico,
rejeição transacional de estados divergentes, comportamento real dos CHECKs/FK/
EXCLUDE, novo upgrade sem mutação e downgrade bloqueado.
Os testes existentes alterados somente acompanham o novo head; suas assertions
sobre revisions históricas e contratos funcionais permanecem preservadas.

Resultado local: PostgreSQL 18.6; 7 testes específicos PASS (incluindo dez
variantes negativas), suíte completa 804 PASS / zero skips. Logs operacionais
ficam fora do repositório. Nenhum HML/PROD foi acessado; nenhum commit foi criado.
