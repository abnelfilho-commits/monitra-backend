"""Pure contracts for administrative identity, without database access."""
import unittest
from types import SimpleNamespace
from uuid import uuid4
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from app.schemas.pessoa import PessoaCreate, PessoaOut
from app.schemas.identidade import AdicionarPapel, AssociarContaLegada, AssociarPapelLegado, IdentidadeComando
from app.services.identidade import constraint_violation


class IdentityContractTests(unittest.TestCase):
    def test_new_person_requires_valid_cpf(self):
        for cpf in (None, '', ' ', '00000000000', '52998224724'):
            with self.subTest(cpf=cpf), self.assertRaises(ValidationError):
                PessoaCreate(nome_completo='Synthetic', cpf=cpf)
        with self.assertRaises(ValidationError):
            PessoaCreate(nome_completo='Synthetic')
        self.assertEqual(PessoaCreate(nome_completo='Synthetic',cpf='529.982.247-25').cpf,'52998224725')

    def test_account_is_not_human_role(self):
        with self.assertRaises(ValidationError):
            AdicionarPapel(chave_idempotencia=uuid4(), motivo='Test', pessoa=dict(nome_completo='Synthetic',cpf='52998224725'), papel='USUARIO')
        for extra in ('senha','senha_hash','perfil','modulo_ids','clinica_id','ativo'):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                IdentidadeComando(chave_idempotencia=uuid4(),motivo='Test',pessoa=dict(nome_completo='Synthetic',cpf='52998224725'),**{extra:'forbidden'})

    def test_legacy_association_requires_explicit_evidence(self):
        values=dict(chave_idempotencia=uuid4(),motivo='Test',pessoa=dict(nome_completo='Synthetic',cpf='52998224725'),registro_id=1)
        with self.assertRaises(ValidationError): AssociarContaLegada(**values)
        values.update(tipo_evidencia='verified',referencia_evidencia='ticket-reference')
        self.assertEqual(AssociarContaLegada(**values).registro_id,1)
        with self.assertRaises(ValidationError): AssociarPapelLegado(**values,papel='USUARIO')
        with self.assertRaises(ValidationError): AssociarContaLegada(**dict(values,tipo_evidencia=' '))

    def test_unique_violation_requires_exact_sqlstate_and_constraint(self):
        original=SimpleNamespace(pgcode='23505',diag=SimpleNamespace(constraint_name='uq_pessoas_cpf'))
        exc=IntegrityError('redacted',{},original)
        self.assertTrue(constraint_violation(exc,'uq_pessoas_cpf'))
        self.assertFalse(constraint_violation(exc,'other'))
        original.pgcode='23503'
        self.assertFalse(constraint_violation(exc,'uq_pessoas_cpf'))
        self.assertFalse(constraint_violation(IntegrityError('redacted',{},Exception()),'uq_pessoas_cpf'))
