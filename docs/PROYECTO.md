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