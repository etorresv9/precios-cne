"""
Evaluación con DeepEval (G-Eval) de la recomendación generada por el LLM.

Cubre los casos 1 y 2 de los 5 requeridos por el proyecto:
  1. Petición válida
  2. Petición válida que cambia una condición relevante (otra ubicación)

Usa como juez el propio Gemini vía Vertex AI (reutiliza la misma
configuración de Google Cloud que ya usa el servicio), para no depender de
una API key de OpenAI adicional.

Los input/actual_output de cada caso son capturas REALES de ejecuciones del
servicio (ver evidencias/sesion-02 y sesion-03), no datos inventados. Si
quieres re-evaluar con una salida más reciente, reemplaza actual_output por
la respuesta actual de tu endpoint.

Ejecutar con:
    pytest tests/test_evaluacion_deepeval.py -v
"""

import os

from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.models import GeminiModel
from deepeval.test_case import LLMTestCase, SingleTurnParams
from dotenv import load_dotenv

load_dotenv()

# --- Modelo juez: el mismo Gemini que usa el servicio, vía Vertex AI ---
juez = GeminiModel(
    model="gemini-3.5-flash",
    project=os.environ["GOOGLE_CLOUD_PROJECT"],
    location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
    use_vertexai=True,
    temperature=0,
)

# --- Métrica: fidelidad de la recomendación a los datos provistos ---
fidelidad_recomendacion = GEval(
    name="FidelidadRecomendacion",
    criteria=(
        "Determina si la 'actual output' (la recomendación) identifica "
        "correctamente al distribuidor con el precio por litro más bajo "
        "entre los datos listados en 'input', sin inventar distribuidores, "
        "precios o ubicaciones que no aparezcan en 'input', y sin omitir "
        "que se trata de reparto a domicilio vía autotanque."
    ),
    evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
    model=juez,
    threshold=0.7,
)


def test_caso_1_peticion_valida():
    """Caso 1: petición válida (Torreón / Albia)."""
    test_case = LLMTestCase(
        input=(
            "Zona: Torreón (Antonio Guerrero)\n"
            "  - Combustibles y Gases de Torreón, S. A. de C. V. (permiso LP/13727/DIST/PLA/2016): $10.94/litro\n"
            "  - Intergas del Norte, S.A. de C.V. (permiso LP/14188/DIST/PLA/2016): $10.94/litro\n"
            "  - GRUPO CENTURION COMBUSTIBLES, S.A.P.I. DE C.V. (permiso LP/14894/DIST/PLA/2016): $10.88/litro\n"
            "\n"
            "Zona: Albia\n"
            "  - GRUPO CENTURION COMBUSTIBLES, S.A.P.I. DE C.V. (permiso LP/14894/DIST/PLA/2016): $10.88/litro\n"
        ),
        actual_output=(
            "Te conviene pedirle el servicio a GRUPO CENTURION COMBUSTIBLES "
            "(permiso LP/14894/DIST/PLA/2016), disponible tanto en Torreón "
            "(Antonio Guerrero) como en Albia. Ofrece el precio más bajo "
            "verificado de la ruta a $10.88/litro."
        ),
    )
    assert_test(test_case, [fidelidad_recomendacion])


def test_caso_2_peticion_valida_condicion_distinta():
    """Caso 2: petición válida cambiando una condición (otra ubicación distinta)."""
    test_case = LLMTestCase(
        input=(
            "Zona: Saltillo\n"
            "  - Mercantil Distribuidora, S. A. de C. V. (permiso LP/14146/DIST/PLA/2016): $9.99/litro\n"
            "  - Hidro Gas de Coahuila, S.A. de C.V. (permiso LP/14304/DIST/PLA/2016): $10.76/litro\n"
        ),
        actual_output=(
            "Te conviene pedirle el servicio a Mercantil Distribuidora "
            "(permiso LP/14146/DIST/PLA/2016), que ofrece el precio más "
            "bajo en Saltillo a $9.99/litro, $0.77 menos que la siguiente "
            "opción disponible."
        ),
    )
    assert_test(test_case, [fidelidad_recomendacion])