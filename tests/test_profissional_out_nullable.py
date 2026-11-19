"""Regression for nullable clinic in responses; no HTTP or database."""
import asyncio
import unittest
from fastapi.exceptions import ResponseValidationError
from fastapi.routing import serialize_response
from fastapi.utils import create_model_field
from pydantic import ValidationError
from app.schemas.profissional import ProfissionalBase, ProfissionalCreate, ProfissionalUpdate, ProfissionalOut


class ProfissionalResponseTests(unittest.TestCase):
    def payload(self, clinic):
        return {'id':1,'nome':'Profissional sintético','ativo':True,'clinica_id':clinic}

    def test_output_accepts_null(self):
        self.assertIsNone(ProfissionalOut.model_validate(self.payload(None)).clinica_id)

    def test_output_accepts_integer(self):
        self.assertEqual(ProfissionalOut.model_validate(self.payload(3)).clinica_id,3)

    def test_output_field_remains_required(self):
        payload=self.payload(None);del payload['clinica_id']
        with self.assertRaises(ValidationError):ProfissionalOut.model_validate(payload)

    def test_creation_update_and_base_still_require_non_null_clinic(self):
        for schema in (ProfissionalBase,ProfissionalCreate,ProfissionalUpdate):
            valid={'nome':'Sintético','clinica_id':3,'senha':'LOCAL_TEST_ONLY','modulo_ids':[1]}
            with self.subTest(schema=schema.__name__):
                self.assertEqual(schema.model_validate(valid).clinica_id,3)
                with self.assertRaises(ValidationError):schema.model_validate(dict(valid,clinica_id=None))
                del valid['clinica_id']
                with self.assertRaises(ValidationError):schema.model_validate(valid)

    def test_other_required_output_fields_unchanged(self):
        for field in ('id','nome','ativo'):
            payload=self.payload(None);del payload[field]
            with self.subTest(field=field),self.assertRaises(ValidationError):
                ProfissionalOut.model_validate(payload)

    def test_fastapi_list_response_accepts_active_professional_without_clinic(self):
        field=create_model_field(name='Response',type_=list[ProfissionalOut],mode='serialization')
        result=asyncio.run(serialize_response(field=field,response_content=[self.payload(None),self.payload(3)],is_coroutine=True))
        self.assertEqual([r['clinica_id'] for r in result],[None,3])
        self.assertTrue(result[0]['ativo'])

    def test_fastapi_still_rejects_invalid_clinic_type(self):
        field=create_model_field(name='Response',type_=list[ProfissionalOut],mode='serialization')
        with self.assertRaises(ResponseValidationError):
            asyncio.run(serialize_response(field=field,response_content=[self.payload({'invalid':True})],is_coroutine=True))

    def test_json_schema_nullability_only_output(self):
        self.assertIn({'type':'null'},ProfissionalOut.model_json_schema()['properties']['clinica_id']['anyOf'])
        for schema in (ProfissionalCreate,ProfissionalUpdate):
            self.assertEqual(schema.model_json_schema()['properties']['clinica_id']['type'],'integer')
            self.assertIn('clinica_id',schema.model_json_schema()['required'])
