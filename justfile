# =============================================================================
# OMNiBot 2000 - Justfile (Task Runner)
# =============================================================================

# Portabilidad: Detecta el shell según el OS
set windows-shell := ["powershell.exe", "-Command"]
set shell := ["sh", "-c"]

# Variables de entorno por defecto
export PRE_COMMIT_USE_UV := "1"

# -----------------------------------------------------------------------------
# 🛠️ INSTALACIÓN Y SETUP
# -----------------------------------------------------------------------------

# Instala todas las dependencias y prepara los hooks de git
setup:
    uv sync --all-packages --all-groups
    uv run pre-commit install
    uv run detect-secrets scan > .secrets.baseline
    @echo "Setup complete."

# Actualiza uv, los hooks y las dependencias a la última versión permitida
update:
    uv self update
    uv run pre-commit autoupdate
    uv lock --upgrade
    uv sync --all-packages --all-groups
    @echo "Update complete."

# -----------------------------------------------------------------------------
# 🛡️ CALIDAD Y SEGURIDAD
# -----------------------------------------------------------------------------

# Ejecuta todos los guardianes de pre-commit sobre todos los archivos
check:
    uv run pre-commit run --all-files

# Ejecuta el linter (Ruff) con auto-fix y formatea el código
lint:
    uv run ruff check --fix .
    uv run ruff format .

# Ejecuta el tipado estático (mypy + motor Pyright/Pylance) en todo el workspace
typecheck:
    uv run mypy --config-file=pyproject.toml server/src robot/src
    uv run pyright

# Auditoría profunda de seguridad (Ruff S + pip-audit)
audit:
    uv run ruff check --select S server/src robot/src
    uv run pip-audit --local
    @echo "Security audit complete."

# Gate de calidad completo antes de mergear a main (equivalente local de CI)
gate: lint typecheck test audit
    @echo "Gate passed - safe to merge."

# -----------------------------------------------------------------------------
# 🧪 TESTING
# -----------------------------------------------------------------------------

# Ejecuta todos los tests en paralelo
test:
    uv run pytest -n auto

# Ejecuta tests en modo debug (sin xdist, con output verbose)
test-debug:
    uv run pytest -n0 --tb=long -s

# Ejecuta tests en paralelo con cobertura HTML y gate mínimo
test-cov:
    uv run pytest -n auto --cov=server/src --cov=robot/src --cov-report=html --cov-fail-under=80
    @echo "Coverage report: docs/coverage_report/index.html"

# -----------------------------------------------------------------------------
# 🚀 EJECUCIÓN (Workspaces)
# -----------------------------------------------------------------------------

# Verifica y arranca los servicios del proyecto (Ollama + modelos)
services:
    powershell.exe -ExecutionPolicy Bypass -File scripts\services.ps1

# Detiene los servicios del proyecto
services-down:
    powershell.exe -ExecutionPolicy Bypass -File scripts\services.ps1 -Down

# Inicia el Servidor (Cerebro) cargando el archivo .env
run-server:
    uv run --env-file .env --package server serve

# Inicia el Robot (Sentidos) cargando el archivo .env
run-robot:
    uv run --env-file .env --package robot robot

# Valida el pipeline completo: mic → STT → LLM → TTS → speaker
test-pipeline *ARGS:
    uv run --env-file .env python scripts/pipeline_test.py {{ARGS}}

# Configura owner/hijos/PIN local. Requiere run-server y run-robot detenidos
setup-personal *ARGS:
    uv run --env-file .env --package server personal-setup {{ARGS}}

# Prueba el cliente HTTP contra el servidor en ejecucion
test-client *ARGS:
    uv run --env-file .env python scripts/client_test.py {{ARGS}}

# Diagnostica el canal público de voz; no prueba recuperación privada persistente.
memory-test *ARGS:
    uv run --env-file .env python scripts/memory_test.py {{ARGS}}

# Eval de extraccion de memoria contra Ollama real (R8) - requiere just services
eval-memory *ARGS:
    uv run --env-file .env python scripts/eval_consolidation.py {{ARGS}}

# Eval aislado de fidelidad del LLM; requiere provider real, no usa STT/retrieval/TTS
eval-chat *ARGS:
    uv run --env-file .env python scripts/eval_chat.py {{ARGS}}

# Mini-QA de M3: contrato /chat, continuidad, aislamiento y modo interactivo
chat-test *ARGS:
    uv run --env-file .env python scripts/chat_test.py {{ARGS}}

# Demo V0: webcam -> /vision/describe (requiere server con VISION_ENABLED=true)
vision-demo *ARGS:
    uv run --env-file .env python scripts/vision_demo.py {{ARGS}}

# Demo visual scene-only: webcam/foto -> /vision/respond (requiere server)
faces-demo *ARGS:
    uv run --env-file .env python scripts/faces_demo.py {{ARGS}}

# Enrola/revoca la cara del owner para autenticacion (Plan 0029, requiere PIN local)
face-auth-demo *ARGS:
    uv run --env-file .env python scripts/face_auth_demo.py {{ARGS}}

# Descarga una vez el modelo Silero VAD (R1) - dependencia efimera, no toca pyproject.toml
fetch-vad-model *ARGS:
    uv run --with silero-vad python scripts/fetch_silero_vad_model.py {{ARGS}}

# Resetea la DB del cerebro: exige server apagado, respalda y borra (seguro)
reset-db:
    powershell.exe -ExecutionPolicy Bypass -File scripts\reset_db.ps1

# -----------------------------------------------------------------------------
# 📦 RELEASE Y VERSIONADO
# -----------------------------------------------------------------------------

# Crea un nuevo commit semántico (Conventional Commits)
commit:
    uv run cz commit

# Lanza una nueva versión (bump version, changelog, tag)
release:
    uv run cz bump

# -----------------------------------------------------------------------------
# 📚 DOCUMENTACIÓN
# -----------------------------------------------------------------------------

# Sirve la documentación localmente con MkDocs
docs:
    uv run --group docs mkdocs serve

# Construye la documentación estática
docs-build:
    uv run --group docs mkdocs build
