# Comparador de precios de Gas LP a domicilio (autotanque)

Proyecto final — Curso de integración con LLM

**Estudiante:** [Tu nombre]

## El caso

Un consumidor con tanque estacionario en casa o negocio quiere decidir a qué
distribuidor pedirle que mande un camión (autotanque) a llenarlo, sin tener
que investigar precios manualmente en varias fuentes. El servicio consulta
datos públicos oficiales de la Comisión Nacional de Energía (CNE) para
varias ubicaciones, filtra precios inválidos o atípicos, y usa un modelo de
lenguaje (Gemini 3.5 Flash) para redactar una recomendación clara a partir
de esos datos ya verificados.

- **API externa:** CNE — endpoint público `api-reportediario.cne.gob.mx`
  (sin autenticación), descubierto inspeccionando la página de consulta de
  precios de Gas LP: https://www.cne.gob.mx/ConsultaPrecios/GasLP/PlantaDistribucion.html
- **Entrada:** una lista de ubicaciones (entidad/municipio/localidad, según
  el catálogo de la CNE).
- **Salida:** distribuidores con precio por litro, por ubicación, más una
  recomendación en texto sobre a quién pedirle el servicio a domicilio.
- **Qué aporta el LLM:** interpreta los precios ya validados y redacta una
  recomendación breve para el consumidor; no decide qué consultar ni puede
  alterar los datos.
- **Qué valida el código:** formato de los IDs de ubicación, cantidad mínima
  de ubicaciones, rango razonable de precio, autorización por API key, y
  reintentos ante fallos intermitentes de la CNE.

## Requisitos previos

- Python 3.12
- Una cuenta de Google Cloud con **Vertex AI (Gemini Enterprise Agent
  Platform)** habilitado, y una cuenta de servicio con rol `Vertex AI User`
- Una cuenta en [Langfuse](https://cloud.langfuse.com) (para trazabilidad)

## Instalación

```bash
git clone <url-de-tu-repositorio>
cd proyecto-final
pip install -r requirements.txt --break-system-packages
```

## Configuración

1. Copia la plantilla de variables de entorno:
   ```bash
   cp .env.example .env
   ```

2. Coloca el JSON de tu cuenta de servicio de Google Cloud en `./secrets/vertex-sa.json`
   (crea la carpeta `secrets/` si no existe; está excluida en `.gitignore`).

3. Edita `.env` y completa:

   | Variable | Descripción |
   |---|---|
   | `API_KEY` | Clave propia del servicio (genera una con `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`) |
   | `GOOGLE_APPLICATION_CREDENTIALS` | Ruta al JSON de la cuenta de servicio, ej. `./secrets/vertex-sa.json` |
   | `GOOGLE_CLOUD_PROJECT` | ID de tu proyecto de Google Cloud |
   | `GOOGLE_CLOUD_LOCATION` | Región de Vertex AI, ej. `us-central1` o `global` |
   | `LANGFUSE_PUBLIC_KEY` | Desde Langfuse → Settings → API Keys |
   | `LANGFUSE_SECRET_KEY` | Desde Langfuse → Settings → API Keys |
   | `LANGFUSE_HOST` | `https://cloud.langfuse.com` (o `https://us.cloud.langfuse.com`) |

## Arranque

```bash
uvicorn main:app --reload
```

El servicio queda disponible en `http://127.0.0.1:8000`. La documentación
interactiva (Swagger) está en `http://127.0.0.1:8000/docs`.

## Prueba

Con el servicio corriendo, en otra terminal:

```bash
curl -X POST http://127.0.0.1:8000/comparar-ruta \
  -H "Content-Type: application/json" \
  -H "X-API-Key: TU_API_KEY_AQUI" \
  -d '{
    "paradas": [
      {"entidad_id": "05", "municipio_id": "035", "localidad_id": "448", "etiqueta": "Torreón (Antonio Guerrero)"},
      {"entidad_id": "05", "municipio_id": "035", "localidad_id": "143", "etiqueta": "Albia"}
    ]
  }'
```

Una respuesta exitosa incluye, por ubicación, los distribuidores con precio
por litro, más una `recomendacion` en texto y un `langfuse_trace_id` para
verificar la traza en Langfuse.

### Mediciones (sesión 3)

```bash
python medir.py
```

Ejecuta la misma solicitud 5 veces de forma secuencial y guarda el resultado
en `evidencias/sesion-03/mediciones.json`, incluyendo el desglose de tiempo
entre la consulta a la CNE y la llamada al LLM.

## Detención

`Ctrl+C` en la terminal donde corre `uvicorn`.

## Estructura del proyecto

```text
proyecto-final/
  README.md
  .gitignore
  .env.example
  requirements.txt
  schemas.py          # Contrato Pydantic (entrada/salida/errores)
  cne_client.py         # Cliente de la API pública de la CNE
  llm_client.py          # Cliente de Gemini 3.5 Flash (Vertex AI)
  main.py                # Endpoint FastAPI
  medir.py               # Script de mediciones (sesión 3)
  docs/
    PROYECTO.md           # Ficha del caso, diagrama de arquitectura, decisiones
  evidencias/
    sesion-02/
    sesion-03/
    sesion-04/
    sesion-05/
    final/
```

## Notas conocidas

- La API de la CNE presenta una tasa de fallo intermitente (~30-40% en
  pruebas) con el error `"Referencia a objeto no establecida..."`. El
  cliente reintenta hasta 5 veces con backoff exponencial y headers
  explícitos (`Accept-Language`), lo que redujo pero no eliminó el problema.
  Ver `docs/PROYECTO.md` para el análisis completo.