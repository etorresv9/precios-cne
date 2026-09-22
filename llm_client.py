"""
Cliente del LLM (Gemini 3.5 Flash vía Vertex AI / Gemini Enterprise Agent Platform)
usado para generar la recomendación final a partir de los precios ya validados.
"""

import os

from google import genai

from schemas import ResultadoParada

MODELO_LLM = "gemini-3.5-flash"


def _construir_cliente() -> genai.Client:
    return genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )


def _construir_prompt(resultados: list[ResultadoParada]) -> str:
    """
    Arma un prompt determinista a partir de datos YA validados por el código.
    El LLM solo interpreta y redacta; no se le pide que invente cifras.
    """
    lineas = [
        "Eres un asistente que ayuda a un consumidor a decidir a qué "
        "distribuidor de Gas LP pedirle que mande un camión (autotanque) a "
        "su domicilio para llenar su tanque estacionario.",
        "A continuación tienes los precios por litro (MXN) ya verificados, "
        "por ubicación/zona. No inventes precios ni distribuidores que no "
        "aparezcan en esta lista.",
        "",
    ]

    for resultado in resultados:
        etiqueta = resultado.parada.etiqueta or (
            f"entidad {resultado.parada.entidad_id}/"
            f"municipio {resultado.parada.municipio_id}/"
            f"localidad {resultado.parada.localidad_id}"
        )
        lineas.append(f"Zona: {etiqueta}")
        if not resultado.distribuidores:
            lineas.append("  (sin distribuidores con precio válido reportado)")
        for d in resultado.distribuidores:
            lineas.append(
                f"  - {d.marca_comercial} (permiso {d.numero_permiso}): "
                f"${d.precio_litro:.2f}/litro"
            )
        lineas.append("")

    lineas.append(
        "Redacta una recomendación breve (máximo 4 líneas) indicando a qué "
        "distribuidor conviene pedirle el servicio a domicilio, y por qué, "
        "pensando en un consumidor que quiere llenar su tanque estacionario "
        "sin salir de casa."
    )
    return "\n".join(lineas)


def generar_recomendacion(resultados: list[ResultadoParada]) -> str:
    """Genera la recomendación en texto usando Gemini 3.5 Flash."""
    cliente = _construir_cliente()
    prompt = _construir_prompt(resultados)

    response = cliente.models.generate_content(
        model=MODELO_LLM,
        contents=prompt,
    )
    return response.text