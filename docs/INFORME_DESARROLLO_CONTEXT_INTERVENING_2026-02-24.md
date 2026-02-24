# Informe Desarrollo: Auto-Agregar Constructos a Context/Intervinientes

Fecha y hora: 2026-02-24 10:50:34 -03:00

## Objetivo

Evitar que las proposiciones teóricas introduzcan constructos que no existan como categorías del paradigma. En vez de prohibirlos, el sistema debe **auto-agregarlos** a:

- `context` cuando sean condiciones situacionales/territoriales donde ocurre el fenómeno.
- `intervening_conditions` cuando sean factores que habilitan/restringen estrategias de acción/interacción.

## Cambios Implementados

### 1) Prompt (Step 2 / Paradigma) endurecido

Archivo: `backend/app/prompts/theory_prompts_v2.py`

- Se añadió regla explícita de coherencia:
  - No permitir constructos solo en `propositions`.
  - Si aparecen en proposiciones y no están en `conditions/actions/consequences`, deben incorporarse en `context` o `intervening_conditions`.
- Se amplió el JSON mínimo esperado para incluir `context` e `intervening_conditions`.

### 2) System prompt Straussian (alineamiento)

Archivo: `backend/app/prompts/straussian_model.py`

- Se añadió instrucción de coherencia para que el modelo no deje variables nuevas solo en `propositions`.

### 3) Backend: normalización + repair best-effort

Archivo: `backend/app/engines/theory_engine.py`

- `normalize_paradigm` ahora garantiza claves:
  - `context` y `intervening_conditions` (por defecto listas vacías).
- `validate_paradigm` ahora reporta conteos de `context` y `intervening_conditions` (telemetría/diagnóstico).
- Nuevo repair: `repair_context_intervening(...)`
  - Completa únicamente `context` y `intervening_conditions`.
  - Usa `available_categories` (categorías detectadas del proyecto) y `propositions` para poblar factores faltantes.

Archivo: `backend/app/engines/theory_pipeline.py`

- Se integra el repair de coherencia:
  - Se ejecuta cuando `context` e `intervening_conditions` están vacíos.
  - Se hace merge con deduplicación por nombre (sin romper datos ya presentes).
  - Se registra en `repairs_applied` como `context_intervening`.

## Compatibilidad

- No cambia el contrato del endpoint.
- `context`/`intervening_conditions` ya eran soportados por PPTX (slide “Contexto e Intervinientes”).
- PDF/PNG/XLSX siguen funcionando con listas de strings o dicts que tengan `name`.

