"""
Contrato de entrada/salida del servicio de comparación de precios de Gas LP
por recipiente (cilindro), pensado para consumidores que acuden directamente
a una planta de distribución a cargar, usando datos públicos de la CNE.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ParadaRuta(BaseModel):
    """Un punto identificado por el catálogo de la CNE (entidad/municipio/localidad)."""

    entidad_id: str = Field(..., pattern=r"^\d{2}$", description="Ej. '05' para Coahuila")
    municipio_id: str = Field(..., pattern=r"^\d{3}$", description="Ej. '035'")
    localidad_id: str = Field(..., description="Ej. '448'")
    etiqueta: str | None = Field(None, description="Nombre legible opcional, ej. 'Torreón'")


class ComparacionRutaGasLPRequest(BaseModel):
    """Entrada del endpoint: una o más ubicaciones donde el consumidor podría cargar."""

    paradas: list[ParadaRuta] = Field(
        ..., min_length=2, description="Al menos dos ubicaciones a comparar"
    )


class DistribuidorComparado(BaseModel):
    """Un distribuidor de Gas LP por recipiente en una ubicación, con precio por kg."""

    numero_permiso: str
    marca_comercial: str
    capacidad_kg: float = Field(..., gt=0, description="Capacidad del recipiente/cilindro, en kg")
    precio_kg: float = Field(
        ..., gt=0, le=60, description="Precio por kilogramo; excluye precios atípicos"
    )
    parada_etiqueta: str | None = None


class ResultadoParada(BaseModel):
    """Resultado de la consulta de precios para una ubicación específica."""

    parada: ParadaRuta
    distribuidores: list[DistribuidorComparado]
    precio_kg_minimo: float | None = None
    precio_kg_promedio: float | None = None


class TiemposDiagnostico(BaseModel):
    """
    Desglose de tiempo por etapa, para el requisito de medición del proyecto.
    No forma parte del "resultado de negocio"; es información de diagnóstico.
    """

    tiempo_cne_s: float = Field(..., description="Suma del tiempo de todas las consultas a la CNE, en segundos")
    tiempo_llm_s: float = Field(..., description="Tiempo de la llamada a Gemini, en segundos")
    tiempo_total_s: float = Field(..., description="Tiempo total del endpoint, en segundos")


class ComparacionRutaGasLPResponse(BaseModel):
    """Salida del endpoint: resultados por ubicación + recomendación generada por el LLM."""

    resultados: list[ResultadoParada]
    recomendacion: str = Field(
        ..., description="Texto generado por el LLM a partir de 'resultados'"
    )
    modelo_llm: str = Field(default="gemini-3.5-flash")
    fecha_consulta: datetime
    tiempos: TiemposDiagnostico
    langfuse_trace_id: str | None = None


class ErrorResponse(BaseModel):
    """Forma consistente de error para todos los casos de falla del servicio."""

    codigo: Literal[
        "datos_faltantes",
        "datos_invalidos",
        "sin_autorizacion",
        "api_externa_no_disponible",
        "sin_resultados",
    ]
    mensaje: str
    detalle: str | None = None