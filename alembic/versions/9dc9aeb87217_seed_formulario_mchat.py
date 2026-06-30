"""seed formulario mchat

Revision ID: 9dc9aeb87217
Revises: 8f540aeef03e
Create Date: 2026-06-26 16:09:59.123167

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9dc9aeb87217'
down_revision: Union[str, Sequence[str], None] = '8f540aeef03e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO formularios_modulo (modulo_id, nome, tipo, ativo)
        SELECT 1, 'M-CHAT', 'ASSESSMENT', true
        WHERE NOT EXISTS (
            SELECT 1
            FROM formularios_modulo
            WHERE nome = 'M-CHAT'
              AND modulo_id = 1
        );
    """)

    op.execute("""
        INSERT INTO campos_formulario (
            formulario_id,
            nome_campo,
            label,
            tipo_campo,
            obrigatorio,
            ordem,
            opcoes,
            ativo
        )
        SELECT
            fm.id,
            v.nome_campo,
            v.label,
            'radio',
            true,
            v.ordem,
            '[{"valor":"SIM","label":"Sim"},{"valor":"NAO","label":"Não"}]'::json,
            true
        FROM formularios_modulo fm
        JOIN (
            VALUES
            ('mchat_1', 'Se você apontar para alguma coisa do outro lado do cômodo, seu filho olha para ela?', 1),
            ('mchat_2', 'Você já se perguntou se seu filho poderia ser surdo?', 2),
            ('mchat_3', 'Seu filho brinca de faz de conta?', 3),
            ('mchat_4', 'Seu filho gosta de subir nas coisas?', 4),
            ('mchat_5', 'Seu filho faz movimentos incomuns com os dedos perto dos olhos?', 5),
            ('mchat_6', 'Seu filho aponta com um dedo para pedir algo ou para obter ajuda?', 6),
            ('mchat_7', 'Seu filho aponta com um dedo para mostrar algo interessante?', 7),
            ('mchat_8', 'Seu filho se interessa por outras crianças?', 8),
            ('mchat_9', 'Seu filho mostra coisas trazendo-as ou segurando-as para você ver?', 9),
            ('mchat_10', 'Seu filho responde quando você o chama pelo nome?', 10),
            ('mchat_11', 'Quando você sorri para seu filho, ele sorri de volta?', 11),
            ('mchat_12', 'Seu filho fica incomodado com barulhos do dia a dia?', 12),
            ('mchat_13', 'Seu filho anda?', 13),
            ('mchat_14', 'Seu filho olha nos seus olhos quando você fala com ele, brinca com ele ou o veste?', 14),
            ('mchat_15', 'Seu filho tenta imitar o que você faz?', 15),
            ('mchat_16', 'Se você virar a cabeça para olhar alguma coisa, seu filho olha em volta para ver o que você está olhando?', 16),
            ('mchat_17', 'Seu filho tenta fazer você olhar para ele?', 17),
            ('mchat_18', 'Seu filho entende quando você pede para ele fazer alguma coisa?', 18),
            ('mchat_19', 'Se algo novo acontece, seu filho olha para seu rosto para ver como você se sente?', 19),
            ('mchat_20', 'Seu filho gosta de atividades de movimento?', 20)
        ) AS v(nome_campo, label, ordem)
            ON true
        WHERE fm.nome = 'M-CHAT'
          AND fm.modulo_id = 1
          AND NOT EXISTS (
              SELECT 1
              FROM campos_formulario cf
              WHERE cf.formulario_id = fm.id
                AND cf.nome_campo = v.nome_campo
          );
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM campos_formulario
        WHERE formulario_id IN (
            SELECT id
            FROM formularios_modulo
            WHERE nome = 'M-CHAT'
              AND modulo_id = 1
        )
        AND nome_campo LIKE 'mchat_%';
    """)

    op.execute("""
        DELETE FROM formularios_modulo
        WHERE nome = 'M-CHAT'
          AND modulo_id = 1
          AND NOT EXISTS (
              SELECT 1
              FROM campos_formulario
              WHERE campos_formulario.formulario_id = formularios_modulo.id
          );
    """)