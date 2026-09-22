"""
Cliente para la API pública de la Comisión Nacional de Energía (CNE):
precios de Gas LP por recipiente (cilindro), reportados por permisionarios
de Planta de Distribución para venta directa al consumidor.

Endpoint descubierto inspeccionando las peticiones de red de:
https://www.cne.gob.mx/ConsultaPrecios/GasLP/PlantaDistribucion.html
"""

import asyncio
import logging

import httpx

from schemas import DistribuidorComparado, ParadaRuta

logger = logging.getLogger("cne_client")

TIMEOUT_S = 20.0
MAX_INTENTOS = 5
ESPERA_BASE_S = 1.5  # backoff exponencial: 1.5s, 3s, 6s, 12s entre intentos

BASE_URL = "https://api-reportediario.cne.gob.mx/api/PlantaDistribucion/precio"

# Techo razonable de precio por KILOGRAMO (pesos MXN) para descartar precios
# atípicos como el 0.01 observado en el feed. Ajustar si el mercado cambia.
PRECIO_KG_MAXIMO_RAZONABLE = 60.0


class CNEAPIError(Exception):
    """La API externa de la CNE no respondió o respondió con un error."""


async def consultar_precios_recipiente(parada: ParadaRuta) -> list[DistribuidorComparado]:
    """
    Consulta los precios de Gas LP por recipiente (cilindro) para una
    ubicación específica y devuelve solo los registros con precio válido.
    """
    params = {
        "entidadId": parada.entidad_id,
        "municipioId": parada.municipio_id,
        "localidadId": parada.localidad_id,
    }

    headers = {
        "Accept": "application/json",
        "Accept-Language": "es-MX,es;q=0.9",
        "User-Agent": "Mozilla/5.0 (compatible; proyecto-final-llm/0.1)",
    }

    ultimo_error: Exception | None = None
    data: dict | None = None

    for intento in range(1, MAX_INTENTOS + 1):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
                response = await client.get(BASE_URL, params=params, headers=headers)
                response.raise_for_status()
            data = response.json()

            if data.get("Success"):
                break  # éxito real, salimos del ciclo de reintentos

            # La CNE respondió 200 pero con Success=false (ej. el error
            # intermitente "Referencia a objeto no establecida..."). Esto
            # NO es un httpx.HTTPError, así que hay que tratarlo aquí
            # explícitamente para que también dispare un reintento.
            errores = data.get("Errors")
            ultimo_error = CNEAPIError(f"La CNE reportó un error: {errores}")
            logger.warning(
                "Intento %d/%d: la CNE respondió Success=false para params=%s (%s)",
                intento, MAX_INTENTOS, params, errores,
            )
            data = None
        except httpx.HTTPError as exc:
            ultimo_error = exc
            logger.warning(
                "Intento %d/%d falló para params=%s (%s)",
                intento, MAX_INTENTOS, params, type(exc).__name__,
            )

        if data is None and intento < MAX_INTENTOS:
            espera = ESPERA_BASE_S * (2 ** (intento - 1))
            logger.info("Reintentando en %.1fs (backoff exponencial)...", espera)
            await asyncio.sleep(espera)

    if data is None:
        # Se agotaron los reintentos sin éxito.
        logger.exception("Falló la consulta a la CNE tras %d intentos, params=%s", MAX_INTENTOS, params)
        raise CNEAPIError(
            f"No se pudo consultar la CNE tras {MAX_INTENTOS} intentos: {ultimo_error!r}"
        ) from ultimo_error

    recipientes = data.get("Value", {}).get("Recipientes", []) or []

    distribuidores: list[DistribuidorComparado] = []
    for item in recipientes:
        precio = item.get("Precio")
        capacidad = item.get("CapacidadRecipiente")
        # Filtro de control: descarta precios o capacidades inválidas/atípicas
        # ANTES de que lleguen al LLM o a la respuesta final.
        if precio is None or precio <= 0 or precio > PRECIO_KG_MAXIMO_RAZONABLE:
            continue
        if capacidad is None or capacidad <= 0:
            continue

        # .get(..., default) no cubre el caso en que la llave existe pero su
        # valor es explícitamente null en el JSON; por eso el "or" adicional.
        numero_permiso = item.get("NumeroPermiso") or "desconocido"
        marca_comercial = item.get("MarcaComercial") or "desconocido"

        distribuidores.append(
            DistribuidorComparado(
                numero_permiso=numero_permiso,
                marca_comercial=marca_comercial,
                capacidad_kg=capacidad,
                precio_kg=precio,
                parada_etiqueta=parada.etiqueta,
            )
        )

    return distribuidores