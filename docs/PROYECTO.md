# Proyecto Final — Comparador de precios de Gas LP a domicilio (autotanque)

## Ficha del caso

**Usuario:** Un consumidor de Gas LP con tanque estacionario (instalado en
su casa o negocio) que quiere decidir a qué distribuidor pedirle que mande
un camión (autotanque) a llenarlo, comparando precios entre varias zonas o
distribuidores disponibles.

**Entrada:** Una lista de ubicaciones (entidad/municipio/localidad del
catálogo de la CNE) que el consumidor está dispuesto a considerar.

Ejemplo:
```json
{
  "paradas": [
    {"entidad_id": "05", "municipio_id": "035", "localidad_id": "448", "etiqueta": "Torreón (Antonio Guerrero)"},
    {"entidad_id": "05", "municipio_id": "035", "localidad_id": "143", "etiqueta": "Albia"}
  ]
}
```

**Salida:** Por cada ubicación, los distribuidores disponibles con su precio
por litro, más una recomendación en texto sobre a quién conviene pedirle el
servicio a domicilio y por qué.

Ejemplo (resumido):
```json
{
  "resultados": [
    {
      "parada": {"etiqueta": "Torreón (Antonio Guerrero)"},
      "distribuidores": [
        {"marca_comercial": "GRUPO CENTURION COMBUSTIBLES, S.A.P.I. DE C.V.", "precio_litro": 10.88}
      ],
      "precio_litro_minimo": 10.88
    }
  ],
  "recomendacion": "Te conviene pedirle el servicio a...",
  "modelo_llm": "gemini-3.5-flash"
}
```

**Qué aporta el LLM:** Interpreta los precios ya validados y redacta la
recomendación en lenguaje natural — no decide qué consultar ni puede
inventar cifras que no estén en los datos.

**Qué valida el código:** Formato de los IDs de ubicación (regex), mínimo 2
ubicaciones, rango razonable de precio (`$0 < precio_litro ≤ $50`),
autorización por API key, y reintentos ante fallos intermitentes de la CNE.

**Qué pasa si falla:** Si la CNE no responde tras 5 intentos →
`502 api_externa_no_disponible`; si ninguna ubicación tiene distribuidores
válidos → `404 sin_resultados`; si los datos de entrada están mal formados
→ `422 datos_invalidos` / `datos_faltantes`; sin API key válida → `401
sin_autorizacion`.

## Diagrama de arquitectura

```mermaid
flowchart TD
    A[Cliente HTTP] -->|POST /comparar-ruta<br/>+ X-API-Key| B{Autorización}
    B -->|inválida/ausente| B1[401 sin_autorizacion]
    B -->|válida| C{Validación Pydantic<br/>ComparacionRutaGasLPRequest}
    C -->|paradas < 2 o IDs mal formados| C1[422 datos_invalidos /<br/>datos_faltantes]
    C -->|válida| D[Por cada ubicación/zona]

    D --> E[Consulta API CNE<br/>api-reportediario.cne.gob.mx<br/>AutoTanques, con reintentos + backoff]
    E -->|falla tras 5 intentos| E1[502 api_externa_no_disponible]
    E -->|responde| F[Filtro: 0 < precio_litro ≤ 50]

    F --> G{¿Alguna ubicación<br/>con distribuidores?}
    G -->|no| G1[404 sin_resultados]
    G -->|sí| H[Construir prompt determinista<br/>con datos ya validados]

    H --> I[Gemini 3.5 Flash<br/>vía Vertex AI]
    I --> J[Recomendación en texto:<br/>a quién pedirle el camión]

    J --> K[Respuesta: ComparacionRutaGasLPResponse<br/>resultados + recomendación + tiempos + trace_id]

    E -.trazado.-> L[(Langfuse)]
    I -.trazado.-> L

    style B1 fill:#f88,stroke:#900
    style C1 fill:#f88,stroke:#900
    style E1 fill:#f88,stroke:#900
    style G1 fill:#f88,stroke:#900
    style K fill:#9f9,stroke:#090
    style L fill:#ddf,stroke:#339
```

## Justificación del patrón

Se eligió un **flujo lineal y controlado** (el código decide qué consultar,
el LLM solo interpreta) en vez de dar al modelo la capacidad de decidir qué
llamar (tool calling / function calling). Los datos vienen de una fuente
**regulada por el gobierno mexicano** (CNE), y el valor del servicio depende
de que el precio mostrado sea exactamente el reportado oficialmente — no una
aproximación que el modelo decida buscar o interpretar por su cuenta.

El LLM entra únicamente **después** de que el código ya validó, consultó y
filtró los datos; su única función es redactar la recomendación en lenguaje
natural, dirigida a un consumidor que va a pedir el servicio por teléfono o
app, a partir de información que ya no puede alterar.

## Decisión: precio por autotanque (litro) en vez de precio por recipiente (kg)

La CNE reporta dos tarifas distintas para Gas LP en su endpoint de Planta de
Distribución: `AutoTanques` (precio por litro, para reparto a domicilio vía
camión hacia un tanque estacionario) y `Recipientes` (precio por
kilogramo, para consumidores que llevan su propio cilindro a la planta). El
proyecto usa `AutoTanques`, ya que el caso final es ayudar a un consumidor
que **no se traslada** — decide, desde su casa, a qué distribuidor pedirle
que le manden el camión a llenar su tanque estacionario.

(Se consideró previamente el escenario de `Recipientes`, para un consumidor
que acude en persona a cargar su cilindro; se descartó a favor de este
enfoque de reparto a domicilio, más representativo del uso típico de Gas LP
en hogares mexicanos.)

## Hallazgo: inestabilidad de la API de la CNE

La API de la CNE presenta una tasa de fallo intermitente (~30-40% en
pruebas) con el error interno `"Referencia a objeto no establecida..."`. Se
implementaron reintentos con backoff exponencial (5 intentos, hasta ~22s) y
headers explícitos (`Accept-Language`) que redujeron la tasa de fallo
original (~100% sin los headers) pero no la eliminaron por completo. Se
considera un riesgo operativo documentado del proveedor, no un defecto del
servicio propio.

## Evaluación (sesión 5)

**Métrica:** G-Eval (`FidelidadRecomendacion`), evaluada con el propio
Gemini 3.5 Flash como juez vía Vertex AI. Criterio: la recomendación debe
identificar al distribuidor con el precio por litro más bajo entre los
datos provistos, sin inventar distribuidores, precios o ubicaciones que no
aparezcan en el contexto. Umbral: 0.7.

Para los casos 3, 4 y 5 (contrato y manejo de errores) se usan pruebas
deterministas con `pytest`, ya que no involucran texto generado por el LLM
y deben ser 100% reproducibles — a diferencia del fallo real de la CNE, que
es intermitente y no se puede provocar bajo demanda, por lo que el caso 5
se simula con un mock que reproduce el error real observado.

| # | Caso | Método | Resultado esperado | Resultado obtenido | Conclusión |
|---|---|---|---|---|---|
| 1 | Petición válida (Torreón/Albia) | G-Eval | Recomienda al distribuidor de menor precio, sin inventar datos | PASSED (score ≥ 0.7) | El LLM identifica correctamente el precio mínimo real |
| 2 | Válida, condición distinta (Saltillo) | G-Eval | Igual que el caso 1, con otra ubicación | PASSED (score ≥ 0.7) | Se confirma que el criterio generaliza a datos distintos |
| 3 | Datos faltantes (< 2 paradas) | pytest determinista | `422` antes de tocar la CNE o el LLM | PASSED | Pydantic bloquea la solicitud en el borde del sistema, como se diseñó |
| 4 | Datos inválidos (IDs mal formados) | pytest determinista | `422`, sin llamada externa | PASSED | El regex de `entidad_id`/`municipio_id` rechaza formatos incorrectos |
| 5 | Fallo de proveedor (CNE no responde) | pytest determinista (mock) | `502 api_externa_no_disponible`, sin llamar al LLM | PASSED | El manejo de errores aísla el fallo externo del resto del flujo; corresponde al error real e intermitente documentado arriba |

Evidencia completa: `evidencias/sesion-05/pytest-resultados.txt` y
`evidencias/sesion-05/deepeval-resultados.txt`.

## Plan de operación (borrador)

**Alcance:** Servicio de un solo endpoint (`POST /comparar-ruta`) para uso
interno/demostrativo. No incluye autenticación de usuarios finales más allá
de la API key compartida, ni persistencia de datos (cada solicitud es
independiente).

**Acceso:** Requiere credenciales propias de cada operador:
- Cuenta de servicio de Google Cloud con rol `Vertex AI User` (Gemini)
- Cuenta en Langfuse (trazabilidad)
- API key propia del servicio (`API_KEY` en `.env`)

**Costo estimado:** Dominado por las llamadas a Gemini 3.5 Flash vía Vertex
AI (tarifa por token de entrada/salida) y, en menor medida, por el volumen
de trazas en Langfuse si se excede el tier gratuito. La consulta a la CNE
no tiene costo (API pública sin autenticación). Con el volumen de pruebas
de este proyecto, el costo se mantuvo dentro del nivel gratuito/mínimo de
ambos servicios.

**Mantenimiento:**
- Revisar periódicamente que el endpoint de la CNE
  (`api-reportediario.cne.gob.mx`) siga vigente — ya cambió una vez de
  dominio (de `cre.gob.mx` a `cne.gob.mx`) tras la disolución de la CRE en
  2025, y podría volver a cambiar.
- Vigilar la disponibilidad del modelo `gemini-3.5-flash` en la región de
  Vertex AI configurada, ya que Google actualiza periódicamente qué
  modelos están disponibles por región.

**Responsables:** Emmanuel Torres — desarrollo, configuración y mantenimiento
del servicio.

**Qué hacer ante un fallo:**
- **Fallo de la CNE** (el más frecuente, ~30-40% intermitente): el
  servicio ya reintenta automáticamente; si persiste tras 5 intentos,
  responde `502` de forma controlada. No requiere intervención manual salvo
  que el fallo se vuelva permanente (posible cambio de endpoint).
- **Fallo de Gemini/Vertex AI** (cuota excedida, `429`): reintentar más
  tarde o revisar el tier de facturación del proyecto de Google Cloud.
- **Fallo de Langfuse**: no bloquea el servicio (la instrumentación falla
  de forma silenciosa si las credenciales son inválidas), pero se pierde
  trazabilidad de esas ejecuciones — revisar `LANGFUSE_PUBLIC_KEY` /
  `LANGFUSE_SECRET_KEY` en `.env`.