"""Explicit-line institutional professional cockpit boundary."""
from fastapi import HTTPException
from app.services.care_lines.access import authorized_line
from app.services.care_lines.exceptions import CareLineCapabilityNotSupported
from app.services.cockpit_professional_composition import COMPOSITIONS


class CockpitProfissionalService:
    @staticmethod
    def get_cockpit(db, usuario, care_line, offset=0, limit=5):
        if usuario.perfil != 'PROFISSIONAL':
            raise HTTPException(403,'Cockpit exclusivo do profissional.')
        line=authorized_line(db,usuario,care_line)
        compose=COMPOSITIONS.get(line.code)
        if not line.supports('cockpit') or compose is None:
            raise HTTPException(400,CareLineCapabilityNotSupported.code)
        return {'care_line':line.code,'module_id':line.module_id,
                'capabilities':{k:v.value for k,v in line.capabilities.items()},
                **compose(db,usuario,line,offset,limit)}
