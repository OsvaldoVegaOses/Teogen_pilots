# Dimensionamiento: concurrencia, servidores y bases de datos

Fecha: 2026-02-27

Resumen
-------
Documento reproducible para estimar usuarios concurrentes, demanda de RPS, instancias de aplicación y dimensionamiento inicial de bases de datos (Postgres, Qdrant, Neo4j). Incluye fórmulas, supuestos, ejemplos y comandos para pruebas de carga.

Fórmulas clave
--------------

- Peticiones por segundo por usuario (rps_por_usuario):
  $$\text{rps\_por\_usuario} = \frac{\text{solicitudes por usuario por minuto}}{60}$$
- RPS total:
  $$\text{RPS\_total} = \text{usuarios\_concurrentes} \times \text{rps\_por\_usuario}$$
- Latencia promedio (seg):
  $$T_{prom} = (1 - f_{heavy})\times T_{simple} + f_{heavy}\times T_{heavy}$$
  donde $f_{heavy}$ es la fracción de peticiones que son "pesadas" (ej. llamadas LLM).
- Concurrency requerida (workers concurrentes):
  $$\text{Concurrency\_requerida} = \text{RPS\_total} \times T_{prom}$$
- Instancias de aplicación necesarias:
  $$\text{Instancias} = \left\lceil\frac{\text{Concurrency\_requerida}}{\text{Concurrency\_por\_instancia}}\right\rceil$$
- Conexiones DB aproximadas:
  $$\text{DB\_conn\_total} = \text{Instancias} \times \text{pool\_db\_por\_instancia}$$

Supuestos razonables (valores por defecto)
-----------------------------------------

- solicitudes_por_usuario_por_minuto = 6 (una cada 10 s) ⇒ rps_por_usuario = 0.1
- T_simple = 0.2 s (endpoints rápidos)
- f_heavy = 0.05 (5% peticiones pesadas)
- T_heavy = 10 s (LLM / pipelines)
- Concurrency_por_instancia (FastAPI async en 2 vCPU / 4 GB) ≈ 40
- pool_db_por_instancia = 20

Ejemplo de cálculo (reproducible)
---------------------------------

1) Calcular $T_{prom}$:

```
T_prom = 0.95*0.2 + 0.05*10 = 0.69 s
```

2) Casos:

- 100 usuarios concurrentes:
  - RPS = 100 * 0.1 = 10 RPS
  - Concurrency = 10 * 0.69 = 6.9 ≈ 7
  - Instancias = ceil(7 / 40) = 1 → recomendar 2 para redundancia

- 500 usuarios concurrentes:
  - RPS = 50
  - Concurrency = 50 * 0.69 = 34.5
  - Instancias = ceil(34.5 / 40) = 1 → recomendar 3 (picos + buffer)

- 2000 usuarios concurrentes:
  - RPS = 200
  - Concurrency = 200 * 0.69 = 138
  - Instancias = ceil(138 / 40) = 4 → recomendar 6 (buffer, autoscale)

Dimensión de bases de datos y servicios
-------------------------------------

Backend API (FastAPI / contenedores)
- Tamaño por instancia: 2 vCPU / 4 GB (inicio)
- Autoscale: min 2, max configurable (p. ej. 10)
- Concurrency_por_instancia: medir con load-test (estimación 40). Reducir si uso memoria o IO es alto.

PostgreSQL
- Usar PgBouncer para pooling si hay >100 conexiones totales.
- Tamaños orientativos:
  - Pequeño (<100 cxs): 2 vCPU / 8 GB
  - Medio (100–300 cxs): 4 vCPU / 16–32 GB
  - Alto (>300 cxs): 8+ vCPU / 32+ GB y réplicas de lectura
- Habilitar replicas de lectura, backups y monitorizar I/O y CPU.

Qdrant (vector DB)
- Desarrollo: 4 vCPU / 16 GB
- Producción moderada: 8 vCPU / 32 GB o cluster HA (3 nodos)
- Disco: NVMe/SSD rápido, snapshots regulares

Neo4j
- Producción moderada: 8 vCPU / 32 GB (tuning de heap/page cache)
- Para alta carga: cluster causal de Neo4j

LLM / Servicios externos
- Las llamadas LLM añaden latencia alta; considerarlas como trabajos asíncronos cuando sea posible.
- Diseñar cola (ej. Redis/Rabbit) y workers que procesen en background para no bloquear API.

Pool DB y conexiones prácticas
-------------------------------

- pool_db_por_instancia recomendado: 15–20
- Configurar PgBouncer en modo `transaction` para soportar muchas instancias con pocas conexiones a Postgres.
- Calcular Max DB connections = pool_total + conexiones internas (monitorizar)

Comandos y tests reproducibles
------------------------------

- Test de carga rápida con `wrk` (endpoint health):

```bash
# instala wrk y corre 60s con 100 conexiones simultaneas
wrk -t4 -c100 -d60s http://localhost:8000/api/health
```

- Prueba de RPS con `hey`:

```bash
hey -z 60s -c 100 -q 10 http://localhost:8000/api/health
```

- Medir endpoints LLM con k6 (ejemplo simple):

```javascript
// script k6.js
import http from 'k6/http';
import { sleep } from 'k6';
export let options = { vus: 50, duration: '1m' };
export default function () {
  http.post('http://localhost:8000/api/llm/generate', JSON.stringify({ input: 'test' }), { headers: { 'Content-Type': 'application/json' } });
  sleep(1);
}
```

- Comando para ejecutar k6:
```
k6 run k6.js
```

Métricas a recolectar
---------------------

- RPS por endpoint
- Latencia p50/p95/p99
- CPU y memoria por instancia
- Concurrency observado (requests in-flight)
- Uso de conexiones DB
- Latencia y errores en Qdrant/Neo4j

Recomendaciones operativas
--------------------------

1. Ejecutar load-tests representativos (endpoints rápidos y pesados). Recalcula la fórmula con Ts reales.
2. Implementar PgBouncer si aún no existe y definir pool por instancia = 15–20.
3. Poner límites de timeout en llamadas externas (LLM/Qdrant) y usar retries con backoff.
4. Desacoplar llamadas LLM con colas para evitar bloquear CPU/threads del API.
5. Configurar autoscaling horizontal del backend y réplicas de lectura para Postgres.
6. Monitorizar métricas y ajustar Concurrency_por_instancia con pruebas de estrés.

Siguientes pasos concretos
--------------------------

- Indícame cuántos usuarios concurrentes quieres dimensionar exactamente y adapto los números.
- Puedo ejecutar (si me das endpoints accesibles) un test de carga local y devolver métricas y recomendación precisa.

Archivo generado automáticamente: `docs/dimensionamiento_infra_concurrencia.md`
