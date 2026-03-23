from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError

from app.routers.analytics import router as analytics_router
from app.routers.usuarios import router as usuarios_router
from app.routers.pacientes import router as pacientes_router
from app.routers.clinicas import router as clinicas_router
from app.routers.auth import router as auth_router
from app.routers.registros import router as registros_router
from app.routers.intervencoes import router as intervencoes_router
from app.routers.timeline import router as timeline_router
from app.routers.me import router as me_router
from app.routers.profissionais import router as profissionais_router

app = FastAPI(title="Monitra API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # depois restringe para o domínio do frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def health():
    return {"status": "ok", "app": "Monitra API"}

@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    return JSONResponse(
        status_code=400,
        content={"detail": "Violação de integridade no banco (verifique IDs e campos)."},
    )

app.include_router(analytics_router)
app.include_router(usuarios_router)
app.include_router(pacientes_router)
app.include_router(clinicas_router)
app.include_router(auth_router)
app.include_router(registros_router)
app.include_router(intervencoes_router)
app.include_router(timeline_router)
app.include_router(me_router)
app.include_router(profissionais_router)
