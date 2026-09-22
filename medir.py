"""
Script de medición para el requisito de la sesión 3: ejecuta la MISMA
solicitud varias veces contra el servicio ya corriendo en local, y registra
tiempo de respuesta, código de estado y errores de cada ejecución.

Incluye el desglose por etapa (tiempo en la CNE vs. tiempo en el LLM) que
ya devuelve el endpoint en el campo "tiempos", para identificar dónde está
el cuello de botella.

Esto NO es una prueba de carga (no se lanzan peticiones concurrentes);
son ejecuciones secuenciales de la misma solicitud, tal como pide el
enunciado del proyecto.

Uso:
    1. Corre el servicio en otra terminal: uvicorn main:app --reload
    2. Ejecuta este script: python medir.py
    3. Revisa el archivo generado en evidencias/sesion-03/mediciones.json
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

URL = "http://127.0.0.1:8000/comparar-ruta"
API_KEY = os.environ.get("API_KEY", "")
NUM_EJECUCIONES = 5  # al menos 3 exige el proyecto; se usan 5 por margen
PAUSA_ENTRE_EJECUCIONES_S = 15  # evita el 429 (RESOURCE_EXHAUSTED) por cuota de Gemini

# La MISMA solicitud se repite en cada ejecución, tal como pide el enunciado.
PAYLOAD = {
    "paradas": [
        {"entidad_id": "05", "municipio_id": "035", "localidad_id": "448", "etiqueta": "Torreón (Antonio Guerrero)"},
        {"entidad_id": "05", "municipio_id": "035", "localidad_id": "143", "etiqueta": "Albia"},
    ]
}

SALIDA = Path("evidencias/sesion-03/mediciones.json")


def ejecutar_medicion(numero: int) -> dict:
    """Ejecuta una sola solicitud y registra tiempo, estado, resultado y desglose por etapa."""
    inicio = time.perf_counter()
    fecha = datetime.now(timezone.utc).isoformat()

    registro = {
        "ejecucion": numero,
        "fecha_hora_utc": fecha,
        "url": URL,
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                URL,
                headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
                json=PAYLOAD,
            )
        duracion_s_cliente = round(time.perf_counter() - inicio, 3)

        registro.update(
            {
                "codigo_http": response.status_code,
                "duracion_s_cliente": duracion_s_cliente,
                "tiempos_servidor": response.json().get("tiempos") if response.is_success else None,
                "error": None if response.is_success else response.text[:500],
            }
        )
    except httpx.HTTPError as exc:
        duracion_s_cliente = round(time.perf_counter() - inicio, 3)
        registro.update(
            {
                "codigo_http": None,
                "duracion_s_cliente": duracion_s_cliente,
                "tiempos_servidor": None,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )

    return registro


def _promedio(valores: list[float]) -> float | None:
    return round(sum(valores) / len(valores), 3) if valores else None


def main() -> None:
    if not API_KEY:
        raise SystemExit(
            "ERROR: no se encontró API_KEY en el entorno. "
            "Verifica que exista un archivo .env en esta carpeta con API_KEY=... "
            "(o expórtala manualmente) antes de correr este script. "
            "Sin esto, todas las ejecuciones fallarán con 401 y la medición no sirve."
        )

    resultados = []
    for i in range(1, NUM_EJECUCIONES + 1):
        resultados.append(ejecutar_medicion(i))
        if i < NUM_EJECUCIONES:
            print(f"Ejecución {i} lista. Esperando {PAUSA_ENTRE_EJECUCIONES_S}s antes de la siguiente...")
            time.sleep(PAUSA_ENTRE_EJECUCIONES_S)

    duraciones_totales = [
        r["duracion_s_cliente"] for r in resultados if r["duracion_s_cliente"] is not None
    ]
    tiempos_cne = [
        r["tiempos_servidor"]["tiempo_cne_s"]
        for r in resultados
        if r.get("tiempos_servidor")
    ]
    tiempos_llm = [
        r["tiempos_servidor"]["tiempo_llm_s"]
        for r in resultados
        if r.get("tiempos_servidor")
    ]

    resumen = {
        "num_ejecuciones": len(resultados),
        "duracion_s_cliente_min": min(duraciones_totales) if duraciones_totales else None,
        "duracion_s_cliente_max": max(duraciones_totales) if duraciones_totales else None,
        "duracion_s_cliente_promedio": _promedio(duraciones_totales),
        "tiempo_s_cne_promedio": _promedio(tiempos_cne),
        "tiempo_s_llm_promedio": _promedio(tiempos_llm),
        "condiciones": {
            "tipo": "ejecuciones secuenciales de la misma solicitud (no es prueba de carga)",
            "entorno": "local",
            "pausa_entre_ejecuciones_s": PAUSA_ENTRE_EJECUCIONES_S,
            "payload": PAYLOAD,
        },
        "ejecuciones": resultados,
    }

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Listo. {len(resultados)} ejecuciones guardadas en {SALIDA}")
    print(
        f"total: min={resumen['duracion_s_cliente_min']}s  "
        f"max={resumen['duracion_s_cliente_max']}s  "
        f"promedio={resumen['duracion_s_cliente_promedio']}s"
    )
    print(
        f"desglose promedio: CNE={resumen['tiempo_s_cne_promedio']}s  "
        f"LLM={resumen['tiempo_s_llm_promedio']}s"
    )


if __name__ == "__main__":
    main()