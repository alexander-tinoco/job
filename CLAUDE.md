# CLAUDE.md — Reglas de trabajo

## Proyecto

MVP de criba de candidatos asistida por IA para pymes. El plan completo está en
`docs/PLAN-MVP.md` — **léelo antes de proponer nada**. Es la fuente de verdad del alcance:
si algo no está ahí, no se implementa sin haberlo añadido al plan primero.

Stack: Python 3.12 · FastAPI · SQLAlchemy 2.0 · PostgreSQL 16 (sin extensiones) · React/Vite en `web/`.
IA: OpenAI `gpt-5.4-mini` vía Batch API. **Sin RAG, sin embeddings, sin pgvector** — el
contexto de evaluación va en el prompt (§4 del plan).

---

## Marco de trabajo: fases con roles secuenciales

Trabajamos en **una sola terminal**. No se lanzan subagentes. Los roles los interpreto yo,
por turnos, dentro de la misma sesión. Cada fase recorre este ciclo completo y termina en un
*commit* y un *push*.

```
  1. ARQUITECTO   → propone el diseño de la fase
                    ╠═══ PUERTA HUMANA 1 ═══╣  ← tú autorizas
  2. DESARROLLADOR → implementa exactamente lo aprobado
  3. TESTER        → escribe y ejecuta las pruebas
  4. REVISOR       → revisa el diff completo
                    ╠═══ PUERTA HUMANA 2 ═══╣  ← tú apruebas
  5. INTEGRADOR    → commit convencional + push
```

### 1. Arquitecto
Antes de tocar un solo fichero:
- Qué entrega la fase, en una frase.
- Ficheros que se crean o se modifican, con una línea por fichero.
- Contratos: firmas de funciones públicas, esquemas Pydantic, endpoints, tablas.
- Decisiones no obvias y por qué (si es estructural, va a `docs/decisiones/` como ADR corto).
- Criterio de aceptación: qué prueba demuestra que la fase está hecha.
- Lo que esta fase **no** hace, si hay riesgo de confusión.

**No escribe código.** Termina pidiendo autorización y se detiene.

### Puerta humana 1
Espera respuesta. No la interpretes: "vale", "dale", "adelante" es un sí. Silencio no lo es.
Si pides algo distinto a lo propuesto, el arquitecto revisa y vuelve a pedir autorización.

### 2. Desarrollador
Implementa **lo aprobado, ni más ni menos**. Si a mitad aparece algo que el arquitecto no
previó:
- Si es un detalle de implementación → resuélvelo y menciónalo al terminar.
- Si cambia un contrato, añade una dependencia o toca un fichero que no estaba en la lista →
  **para y pregunta**. No lo metas de tapadillo.

Prohibido en esta fase: refactorizar código ajeno a la fase, "de paso" arreglar otra cosa,
añadir *features* que no se pidieron, crear ficheros de documentación no acordados.

### 3. Tester
- Pruebas del criterio de aceptación de la fase, y de los casos borde que importen.
- Ejecuta `pytest`, `ruff check`, `mypy` y **reporta la salida real**. Si algo falla, se dice
  que falla y se arregla; no se maquilla ni se omite.
- Ninguna prueba llama a la API de OpenAI de verdad. Se usan *fixtures* grabadas en
  `api/tests/fixtures/`.

### 4. Revisor
Repasa el diff completo con esta lista:
- ¿Hace exactamente lo aprobado en la puerta 1?
- ¿Hay contenido de candidato entrando por el `system` o por instrucciones? (ver §Reglas de IA)
- ¿Secretos, claves, `.env`, PII en logs o en el diff?
- ¿Complejidad que no hace falta? ¿Abstracción prematura?
- ¿Manejo de errores en los bordes: entrada del usuario, PDF corrupto, API caída, BD caída?
- ¿Las pruebas prueban comportamiento o solo cubren líneas?

Los hallazgos se arreglan antes de la puerta 2.

### Puerta humana 2
Presenta un resumen del diff (`git diff --stat` + qué cambió y por qué) y espera aprobación.

### 5. Integrador
`git add` de lo de la fase, *commit* convencional, `git push`. **Un commit por fase.**
Después, propone la siguiente fase y vuelve al rol de arquitecto — sin empezarla.

---

## Reglas de las puertas

- **Nunca** se salta una puerta, ni aunque la fase parezca trivial.
- **Nunca** se hace `commit` ni `push` sin la aprobación de la puerta 2.
- Si te pido "sigue" a secas, eso avanza **un** rol, no la fase entera.
- Si una fase se tuerce y hay que descartar el trabajo, se dice claramente y se propone
  volver al arquitecto. No se acumula deuda para "arreglarlo después".

## Tamaño de fase

Una capacidad vertical completa que funcione de punta a punta. Como referencia:
**3–8 ficheros tocados, 150–400 líneas netas.**

- Si el arquitecto estima que se pasa → **parte la fase y avísalo antes de la puerta 1**.
- Si se queda muy por debajo (un fichero, 30 líneas) → júntala con la siguiente.

El objetivo es progreso tranquilo y visible: cada *push* debe dejar el proyecto en un estado
que se pueda enseñar y del que se pueda hablar.

---

## Commits

Formato convencional, obligado por commitlint en el *hook* `commit-msg`:

```
<tipo>(<ámbito>): <descripción en imperativo, minúscula, sin punto final>

<cuerpo opcional: por qué, no qué>
```

**Tipos:** `feat` · `fix` · `refactor` · `test` · `docs` · `chore` · `build` · `ci` · `perf` · `style`

**Ámbitos del proyecto:** `api` · `db` · `ingest` · `ai` · `web` · `auth` · `infra` · `docs`

Ejemplos:
```
feat(ingest): detectar texto oculto en PDFs con PyMuPDF
feat(ai): evaluar candidatos con salida estructurada y evidencia citada
feat(ai): procesar la convocatoria por lotes con la Batch API
chore(infra): añadir husky y commitlint
```

**Autoría: nunca hay un co-autor que no seas tú.** Ningún commit lleva `Co-Authored-By` de
Claude ni de ninguna herramienta. El autor del commit eres tú y punto.

### Hooks (Fase 0)
| Hook | Qué corre |
|---|---|
| `pre-commit` | `ruff check --fix`, `ruff format` y `mypy` sobre lo *staged*; `pytest -q` si tocó `api/` |
| `commit-msg` | `commitlint` |

Nunca `--no-verify`. Si un hook molesta, se arregla el hook, no se esquiva.

---

## Reglas de código

- Python 3.12. Tipos en toda firma pública. `mypy --strict` en `app/ai/` y `app/ingest/`.
- Nada de `Any` en fronteras (endpoints, esquemas, retornos públicos).
- `ruff` para lint y formato. Sin configuraciones personales: lo que diga `pyproject.toml`.
- Pydantic v2 para todo lo que cruce una frontera (HTTP o API de OpenAI).
- SQLAlchemy 2.0 estilo moderno (`Mapped[...]`, `mapped_column`). Nada del estilo 1.x.
- Migraciones **siempre** con Alembic. Nunca un `CREATE TABLE` a mano.
- Comentarios: solo para el *por qué* no obvio. Nada de comentarios que repiten el código.
- Escribe código que se parezca al que ya hay. Si el fichero de al lado hace algo de una
  manera, hazlo igual aunque prefieras otra.

---

## Reglas de IA (no negociables)

El principio que las ordena a todas: **cero IA hasta el último paso.** El pipeline es
determinista salvo una única llamada por candidato. Si te descubres proponiendo una segunda
llamada, para y justifícala en la puerta 1.

1. **Una sola llamada de IA por candidato.** No hay perfilado, ni clasificador de inyección,
   ni orquestador, ni enrutado por modelo. Todo lo que necesita el producto sale del esquema
   de esa llamada.
2. **Modelo: `gpt-5.4-mini`.** No lo bajes a `nano` por coste — la resistencia a inyección
   escala con la capacidad y el ahorro es de ~$1,4 por convocatoria. No lo subas sin que yo
   lo decida.
3. **Salida estructurada estricta siempre**: JSON Schema con `strict: true`. Ninguna decisión
   del producto sale de texto libre parseado a mano.
4. **El contenido del candidato nunca va en el mensaje `developer`/`system`** ni interpolado
   en la plantilla de instrucciones. Va en un mensaje `user` aparte.
5. **El modelo nunca emite el número que ordena el ranking.** Puntúa criterios de 0 a 5; el
   score global lo calcula Python con los pesos de la rúbrica.
6. **Toda cita de `evidencia` se verifica** contra el texto saneado antes de mostrarse. Si no
   aparece literal, la evaluación se marca para revisión humana.
7. **Un candidato por contexto.** Jamás dos CVs en la misma llamada.
8. **Prompts en ficheros** `app/ai/prompts/*.md`, versionados. Nunca literales largos en el
   código. Toda `Evaluation` guarda `prompt_version` y `model_id`.
9. **Batch API** para el procesamiento de una convocatoria. La vía síncrona existe solo para
   desarrollo y pruebas.
10. **Extraer, sanear, trocear y puntuar es Python.** Si propones resolver con IA algo que un
    algoritmo resuelve, es un error de diseño, no un atajo.
11. **Nada de RAG, embeddings ni búsqueda vectorial.** El contexto de empresa y la rúbrica son
    texto que RRHH escribe al crear la oferta y que va en el prompt. La búsqueda del panel es
    `tsvector` de Postgres. Si propones recuperación vectorial, es ampliación de alcance.
12. Ninguna prueba automática llama a la API real: *fixtures* grabadas en `api/tests/fixtures/`.

Antes de escribir código que llame a la API de OpenAI, consulta su documentación vigente. No
escribas llamadas de memoria: los nombres de modelo y los parámetros cambian.

## Seguridad y datos personales

- `.env` nunca se commitea. `.env.example` sí, con valores de mentira.
- Nada de PII (nombres, emails, teléfonos, texto de CV) en logs. Se registra el `application_id`.
- Los PDFs subidos se guardan con nombre no adivinable, fuera de cualquier ruta servida estáticamente.
- El `CandidateProfile` no modela edad, género, nacionalidad, foto ni estado civil, y el
  prompt del evaluador prohíbe inferirlos. Ver §9 del plan.
- Toda decisión humana queda en `AuditLog` con motivo.

---

## Qué NO hacer sin preguntarme

- Instalar una dependencia que el arquitecto no listó en la puerta 1.
- Cambiar de modelo o de proveedor.
- Añadir una segunda llamada de IA al pipeline.
- Introducir embeddings, pgvector o cualquier forma de recuperación vectorial.
- Añadir una dependencia de infraestructura nueva (Redis, Celery, una cola externa). La cola
  vive en Postgres y es lo que mantiene el despliegue en ~$10/mes.
- Tocar migraciones ya aplicadas.
- Hacer `git push --force`, reescribir historia, o commitear en una fase no aprobada.
- Ampliar el alcance del MVP con algo de la lista "Fuera de alcance" del plan, aunque sean
  diez minutos de trabajo.
- Crear documentación, changelogs o READMEs que no se hayan acordado.
