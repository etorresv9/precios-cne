"""
Servicio HTTP: comparador de precios de Gas LP por autotanque (reparto a
domicilio para llenado de tanque estacionario), usando datos públicos de
la CNE y Gemini 3.5 Flash para la recomendación final.
"""

import os
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from langfuse import Langfuse, observe
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

from cne_client import CNEAPIError, consultar_precios_autotanque
from llm_client import generar_recomendacion
from schemas import (
    ComparacionRutaGasLPRequest,
    ComparacionRutaGasLPResponse,
    ErrorResponse,
    ResultadoParada,
    TiemposDiagnostico,
)

load_dotenv()

langfuse = Langfuse()  # lee LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST del entorno
GoogleGenAIInstrumentor().instrument()

app = FastAPI(
    title="Comparador de precios de Gas LP a domicilio",
    description="Consulta precios reportados a la CNE y recomienda a qué distribuidor pedir el camión a domicilio.",
    version="0.1.0",
)

API_KEY_ESPERADA = os.environ.get("API_KEY")


def _verificar_autorizacion(x_api_key: str | None) -> None:
    """Control de autorización simple por header. Rechaza sin key válida."""
    if not API_KEY_ESPERADA:
        # Si no se configuró ninguna key en el servidor, es un error de
        # configuración, no del cliente: se registra como error de proveedor.
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                codigo="api_externa_no_disponible",
                mensaje="El servicio no tiene configurada una API_KEY.",
            ).model_dump(),
        )
    if x_api_key != API_KEY_ESPERADA:
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(
                codigo="sin_autorizacion",
                mensaje="API key inválida o ausente. Envía el header X-API-Key.",
            ).model_dump(),
        )


@app.post(
    "/comparar-ruta",
    response_model=ComparacionRutaGasLPResponse,
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
)
@observe(name="comparar-ruta")
async def comparar_ruta(
    request: ComparacionRutaGasLPRequest,
    x_api_key: str | None = Header(default=None),
) -> ComparacionRutaGasLPResponse:
    """
    Recibe una o más ubicaciones/zonas y devuelve, por cada una, los
    distribuidores de Gas LP por autotanque con precio válido, más una
    recomendación en texto generada por el LLM sobre a quién pedirle el
    servicio a domicilio.
    """
    _verificar_autorizacion(x_api_key)
    trace_id = langfuse.get_current_trace_id()

    inicio_total = time.perf_counter()
    tiempo_cne_s = 0.0

    resultados: list[ResultadoParada] = []

    for parada in request.paradas:
        inicio_cne = time.perf_counter()
        try:
            distribuidores = await consultar_precios_autotanque(parada)
        except CNEAPIError as exc:
            raise HTTPException(
                status_code=502,
                detail=ErrorResponse(
                    codigo="api_externa_no_disponible",
                    mensaje="No se pudo obtener precios de la CNE para una ubicación.",
                    detalle=str(exc),
                ).model_dump(),
            ) from exc
        finally:
            tiempo_cne_s += time.perf_counter() - inicio_cne

        precios = [d.precio_litro for d in distribuidores]
        resultados.append(
            ResultadoParada(
                parada=parada,
                distribuidores=distribuidores,
                precio_litro_minimo=min(precios) if precios else None,
                precio_litro_promedio=(sum(precios) / len(precios)) if precios else None,
            )
        )

    if all(not r.distribuidores for r in resultados):
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                codigo="sin_resultados",
                mensaje="Ninguna ubicación tiene distribuidores con precio válido.",
            ).model_dump(),
        )

    inicio_llm = time.perf_counter()
    recomendacion = generar_recomendacion(resultados)
    tiempo_llm_s = time.perf_counter() - inicio_llm

    tiempo_total_s = time.perf_counter() - inicio_total

    return ComparacionRutaGasLPResponse(
        resultados=resultados,
        recomendacion=recomendacion,
        fecha_consulta=datetime.now(timezone.utc),
        tiempos=TiemposDiagnostico(
            tiempo_cne_s=round(tiempo_cne_s, 3),
            tiempo_llm_s=round(tiempo_llm_s, 3),
            tiempo_total_s=round(tiempo_total_s, 3),
        ),
        langfuse_trace_id=trace_id,
    )


@app.exception_handler(HTTPException)
async def error_handler(request, exc: HTTPException):
    """Devuelve siempre el detalle en la forma de ErrorResponse."""
    detalle = exc.detail
    if not isinstance(detalle, dict):
        detalle = ErrorResponse(codigo="datos_invalidos", mensaje=str(detalle)).model_dump()
    return JSONResponse(status_code=exc.status_code, content=detalle)