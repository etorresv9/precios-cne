"""
Pruebas deterministas del contrato del servicio.

Cubre los casos 3, 4 y 5 de los 5 requeridos por el proyecto:
  3. Datos faltantes (menos de 2 paradas)
  4. Datos inválidos (IDs con formato incorrecto)
  5. Fallo de proveedor (la CNE no responde)

Estas pruebas NO hacen llamadas reales a la CNE ni a Gemini (el caso 5 usa
un mock), por lo que son rápidas, deterministas y repetibles — a diferencia
de los casos 1 y 2 (evaluados con G-Eval en test_evaluacion_deepeval.py),
que dependen de la calidad del texto generado.

Ejecutar con:
    pytest tests/test_contrato.py -v
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import main
from cne_client import CNEAPIError

client = TestClient(main.app)

API_KEY_VALIDA = main.API_KEY_ESPERADA
HEADERS_VALIDOS = {"X-API-Key": API_KEY_VALIDA} if API_KEY_VALIDA else {}

PARADA_VALIDA_1 = {
    "entidad_id": "05", "municipio_id": "035", "localidad_id": "448", "etiqueta": "Torreón",
}
PARADA_VALIDA_2 = {
    "entidad_id": "05", "municipio_id": "035", "localidad_id": "143", "etiqueta": "Albia",
}


def test_caso_3_datos_faltantes():
    """Caso 3: una sola parada (se requieren al menos 2) → 422 datos_faltantes."""
    respuesta = client.post(
        "/comparar-ruta",
        headers=HEADERS_VALIDOS,
        json={"paradas": [PARADA_VALIDA_1]},
    )
    assert respuesta.status_code == 422
    # No debe haber llegado a consultar la CNE ni al LLM: Pydantic lo
    # rechaza antes de que el código de negocio se ejecute.


def test_caso_3b_datos_faltantes_lista_vacia():
    """Caso 3 (variante): lista de paradas vacía → 422."""
    respuesta = client.post(
        "/comparar-ruta",
        headers=HEADERS_VALIDOS,
        json={"paradas": []},
    )
    assert respuesta.status_code == 422


def test_caso_4_datos_invalidos_ids_mal_formados():
    """Caso 4: entidad_id/municipio_id sin el formato esperado (regex) → 422."""
    respuesta = client.post(
        "/comparar-ruta",
        headers=HEADERS_VALIDOS,
        json={
            "paradas": [
                {"entidad_id": "5", "municipio_id": "35", "localidad_id": "448"},  # sin ceros a la izquierda
                PARADA_VALIDA_2,
            ]
        },
    )
    assert respuesta.status_code == 422


def test_caso_4b_sin_autorizacion():
    """Variante de datos/acceso inválido: sin X-API-Key → 401 sin_autorizacion."""
    respuesta = client.post(
        "/comparar-ruta",
        json={"paradas": [PARADA_VALIDA_1, PARADA_VALIDA_2]},
    )
    assert respuesta.status_code == 401
    assert respuesta.json()["codigo"] == "sin_autorizacion"


@patch("main.consultar_precios_autotanque", new_callable=AsyncMock)
def test_caso_5_fallo_de_proveedor(mock_consultar):
    """
    Caso 5: la CNE falla de forma persistente (simulado con mock, ya que el
    fallo real de la CNE es intermitente y no reproducible bajo demanda).
    Debe responder 502 api_externa_no_disponible sin llegar a llamar al LLM.
    """
    mock_consultar.side_effect = CNEAPIError(
        "No se pudo consultar la CNE tras 5 intentos: simulado para prueba"
    )

    respuesta = client.post(
        "/comparar-ruta",
        headers=HEADERS_VALIDOS,
        json={"paradas": [PARADA_VALIDA_1, PARADA_VALIDA_2]},
    )

    assert respuesta.status_code == 502
    assert respuesta.json()["codigo"] == "api_externa_no_disponible"


@pytest.mark.skipif(
    not API_KEY_VALIDA,
    reason="Requiere API_KEY configurada en el entorno para correr esta prueba",
)
def test_caso_5b_sin_resultados():
    """
    Variante: la CNE responde pero sin distribuidores válidos en ninguna
    ubicación (simulado con mock) → 404 sin_resultados.
    """
    with patch("main.consultar_precios_autotanque", new_callable=AsyncMock) as mock_consultar:
        mock_consultar.return_value = []
        respuesta = client.post(
            "/comparar-ruta",
            headers=HEADERS_VALIDOS,
            json={"paradas": [PARADA_VALIDA_1, PARADA_VALIDA_2]},
        )
    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "sin_resultados"