# Guion de exposición — 5 minutos

**Proyecto:** Comparador de precios de Gas LP a domicilio (autotanque)
**Duración total:** 5:00

---

## Minuto 1 — Usuario, problema, API y alcance

> "Mi proyecto ayuda a un consumidor con tanque estacionario de Gas LP —el
> tanque fijo instalado en casa o negocio— a decidir a qué distribuidor
> pedirle que mande el camión a llenarlo, comparando precios reales entre
> varias zonas.
>
> Los datos vienen de la Comisión Nacional de Energía, el regulador de
> energía en México. Publican los precios que cada distribuidor reporta
> diariamente, y mi servicio los consulta en vivo, los valida, y usa un
> modelo de lenguaje —Gemini 3.5 Flash— para redactar la recomendación
> final.
>
> El alcance es un solo endpoint HTTP, sin autenticación de usuarios
> finales más allá de una API key compartida, pensado como prototipo
> funcional, no como producto listo para producción."

**Mostrar:** el diagrama de arquitectura de `docs/PROYECTO.md` (pantalla completa un momento).

---

## Minuto 2-3 — Demo en vivo

**Antes de empezar, ten abierto:**
- Terminal con `uvicorn main:app --reload` corriendo
- Otra terminal lista para el curl
- `evidencias/sesion-02/consulta-real.json` abierto en otra pestaña **por si falla la conexión en vivo**

> "Voy a mandar una petición real con dos ubicaciones en Torreón."

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

> "Esto acaba de consultar en vivo la API pública de la CNE, filtrar los
> precios inválidos —por ejemplo, la CNE a veces reporta precios en $0.01
> por errores de captura, y mi código los descarta antes de que lleguen al
> modelo—, y le pasó los datos ya limpios a Gemini para que redactara esta
> recomendación."

**Señala en la respuesta JSON:**
- El campo `resultados` → precios reales por ubicación
- El campo `recomendacion` → texto generado por el LLM
- El campo `tiempos` → cuánto tardó cada etapa
- El campo `langfuse_trace_id` → "esto lo puedo buscar en Langfuse para ver el prompt exacto que recibió el modelo"

**Si falla la conexión en vivo:** cambia inmediatamente a `evidencias/sesion-02/consulta-real.json` y di: *"Aquí tienen la ejecución real que guardé como evidencia, con la misma estructura."* No inventes ni simules una respuesta nueva.

---

## Minuto 4 — Medición, evaluación y fallo controlado

> "Corrí la misma solicitud 5 veces para medir tiempos."

**Mostrar `evidencias/sesion-03/mediciones.json`** (o el resumen en consola si lo tienes guardado):

> "El promedio fue de X segundos, y descubrí algo interesante: la mayor
> parte del tiempo lo consume la llamada a Gemini, no la consulta a la
> CNE — [da el número exacto del desglose CNE vs LLM]."

> "Para evaluar la calidad de la recomendación, usé DeepEval con G-Eval,
> usando el propio Gemini como juez, verificando que la recomendación
> identifique correctamente al distribuidor más barato sin inventar datos."

**Mostrar brevemente** `evidencias/sesion-05/deepeval-resultados.txt` (2 passed).

> "Y aquí un fallo real que encontré: la API de la CNE falla de forma
> intermitente —cerca de 30-40% de las veces— con un error interno del
> servidor. Lo reproduzco con una prueba controlada:"

```bash
pytest tests/test_contrato.py::test_caso_5_fallo_de_proveedor -v
```

> "Mi servicio responde con un 502 controlado en vez de romperse, y
> reintenta automáticamente con backoff exponencial antes de darse por
> vencido."

---

## Minuto 5 — Decisiones, límites y mejoras

> "Decisiones clave: dejé que el código, no el modelo, decida qué
> consultar — porque los datos vienen de una fuente regulada, y el valor
> del servicio depende de que el precio sea exactamente el oficial, no una
> aproximación del LLM.
>
> El límite más importante es la inestabilidad de la propia API de la CNE,
> que documenté y mitigué pero no puedo eliminar del todo.
>
> Si tuviera más tiempo, agregaría: caché de resultados recientes para no
> depender de que la CNE responda en cada solicitud, geocodificación para
> aceptar direcciones en vez de IDs de catálogo, y paralelizar las
> consultas cuando hay varias ubicaciones en vez de hacerlas una por una."

---

## Checklist antes de exponer

- [ ] Servicio corriendo (`uvicorn main:app --reload`) y probado 10 minutos antes
- [ ] `.env` con credenciales válidas (Google Cloud, Langfuse, API_KEY)
- [ ] `evidencias/sesion-02/consulta-real.json` abierto como respaldo
- [ ] `evidencias/sesion-03/mediciones.json` con los números a la mano
- [ ] `evidencias/sesion-05/deepeval-resultados.txt` y `pytest-resultados.txt` abiertos
- [ ] `docs/PROYECTO.md` con el diagrama listo para mostrar
- [ ] Cronómetro o reloj visible para no pasarte de 5 minutos
