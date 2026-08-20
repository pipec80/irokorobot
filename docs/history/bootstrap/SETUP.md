# OMNiBot — Setup del Workspace
> **Status:** Historical bootstrap note. It is preserved as project history,
> not as current installation, dependency, CI, or quality instruction.
> Start with [the Iroko technical documentation portal](../../README.md).

This note records the initial workspace construction and may name obsolete commands, dependencies, and hardware assumptions.

> Basado en documentación oficial de uv. Windows PowerShell.

---

## 1. Verificar / instalar uv

```powershell
uv --version
```

Si no está instalado:
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Actualizar:
```powershell
uv self update
```

---

## 2. Instalar Python con uv

```powershell
uv python install 3.12
uv python list
```

---

## 3. Crear la raíz del workspace

```powershell
mkdir omnibot
cd omnibot
uv init
uv python pin 3.12
```

Borrar `main.py` — no se usa.

Estructura inicial:
```
omnibot/
├── .python-version
├── .gitignore
├── README.md
└── pyproject.toml
```

---

## 4. Crear los subproyectos

```powershell
uv init server --package
uv init robot --package
```

uv agrega automáticamente `[tool.uv.workspace]` al `pyproject.toml` raíz.

Estructura final:
```
omnibot/
├── .python-version
├── .gitignore
├── .env                   <- NO va a git
├── README.md
├── pyproject.toml
├── uv.lock                <- SÍ va a git
├── .venv/                 <- NO va a git
├── server/
│   ├── pyproject.toml
│   └── src/server/
│       └── __init__.py
└── robot/
    ├── pyproject.toml
    └── src/robot/
        └── __init__.py
```

---

## 5. pyproject.toml raíz

```toml
[project]
name = "omnibot"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[tool.uv.workspace]
members = ["server", "robot"]

[dependency-groups]
lint = ["ruff>=0.4.0"]

[tool.ruff]
line-length = 88
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

> Configuración de uv solo en la raíz. En workspaces, uv ignora
> `[tool.uv]` de los subproyectos.

---

## 6. pyproject.toml servidor

```toml
[project]
name = "server"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.111.0",
    "uvicorn>=0.30.0",
    "faster-whisper>=1.0.0",
    "ollama>=0.2.0",
    "piper-tts>=1.2.0",
    "python-multipart>=0.0.9",
]

[build-system]
requires = ["uv_build>=0.11.7,<0.12"]
build-backend = "uv_build"

[project.scripts]
server = "server.main:main"
```

---

## 7. pyproject.toml robot

```toml
[project]
name = "robot"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "sounddevice>=0.4.7",
    "numpy>=1.26.0",
    "httpx>=0.27.0",
]

[build-system]
requires = ["uv_build>=0.11.7,<0.12"]
build-backend = "uv_build"

[project.scripts]
robot = "robot.audio_capture:main"
```

---

## 8. Variables de entorno — .env

Crear `omnibot/.env`:

```env
WHISPER_MODEL=medium
OLLAMA_HOST=http://localhost:11434
PIPER_VOICE=es_ES-sharvard-medium
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
```

Ejecutar con variables cargadas:
```powershell
uv run --env-file .env --package server server
```

Si la misma variable existe en el sistema y en `.env`, gana la del sistema.
Nunca commitear `.env` — ya está en `.gitignore` generado por uv.

---

## 9. Agregar dependencias

```powershell
# Servidor
cd server
uv add fastapi uvicorn faster-whisper ollama python-multipart
cd ..

# Robot
cd robot
uv add sounddevice numpy httpx
cd ..

# Ruff como dev dependency del workspace
uv add --group lint ruff
```

---

## 10. Sincronizar el entorno

```powershell
uv sync --all-groups
```

---

## 11. Activar entorno en Windows

```powershell
.venv\Scripts\activate
```

O ejecutar sin activar:
```powershell
uv run python -c "import fastapi; print('ok')"
```

---

## 12. Archivos fuente a crear

```
server/src/server/
├── __init__.py
├── main.py
├── stt.py
├── llm.py
└── tts.py

robot/src/robot/
├── __init__.py
├── audio_capture.py
└── server_client.py
```

---

## Comandos de uso diario

```powershell
# Correr servidor
uv run --env-file .env --package server server

# Correr robot
uv run --env-file .env --package robot robot

# Linter (uv run, no uvx — ruff necesita ver el proyecto)
uv run ruff check .
uv run ruff format .

# Árbol de dependencias
uv tree

# Actualizar un paquete específico
uv lock --upgrade-package fastapi

# Re-sync forzado
uv sync --reinstall

# Actualizar uv
uv self update
```

---

## Variables de entorno de uv — las que importan al proyecto

Estas controlan el comportamiento de uv, no de la app. Se setean
en PowerShell o en el perfil de usuario, no en `.env`.

```powershell
# Cambiar dónde guarda el cache (útil si C: tiene poco espacio)
$env:UV_CACHE_DIR = "D:\uv-cache"

# Forzar uso offline (sin descargas)
$env:UV_OFFLINE = "1"

# Deshabilitar carga del .env (para pruebas limpias)
$env:UV_NO_ENV_FILE = "1"

# Usar Python del sistema en lugar del administrado por uv
$env:UV_PYTHON = "python3.12"
```

---

## Ubicaciones de storage en Windows

Útil cuando necesitas encontrar archivos manualmente o liberar espacio.

| Qué | Ruta |
|---|---|
| Cache de paquetes | `%LOCALAPPDATA%\uv\cache` |
| Datos persistentes (Python, tools) | `%APPDATA%\uv\data` |
| Config de usuario | `%APPDATA%\uv\uv.toml` |
| Ejecutables (ruff, etc.) | `%USERPROFILE%\.local\bin` |
| .venv del proyecto | `omnibot\.venv\` |

```powershell
# Ver rutas exactas en tu máquina
uv cache dir
uv python dir
uv tool dir
```

> Importante: el cache debe estar en el mismo disco que el `.venv`
> para que uv pueda hacer hardlinks en vez de copias. Si los mueves
> a discos distintos, las instalaciones serán más lentas.

---

## Gestión del cache

```powershell
# Ver tamaño y ubicación
uv cache dir

# Limpiar un paquete específico
uv cache clean faster-whisper

# Limpiar todo
uv cache clean

# Eliminar entradas no usadas — seguro, correr periódicamente
uv cache prune

# Forzar re-descarga sin limpiar cache
uv sync --refresh
```

---

## Troubleshooting — Build failures

uv construye un paquete desde el source cuando no existe un wheel precompilado
para tu plataforma. Esto puede fallar si faltan dependencias del sistema.

**Cómo reconocer un build failure:**
El error dice `The build backend returned an error` — el error no es de uv,
es del paquete que se está intentando compilar.

**Paquetes del proyecto que pueden necesitar compilación:**

| Paquete | Por qué | Solución Windows |
|---|---|---|
| `sounddevice` | Necesita PortAudio | Instalar `pipwin` o usar wheel precompilado |
| `faster-whisper` | Necesita CTranslate2 | Generalmente tiene wheels, pero verificar |
| `numpy` | Extensiones C | Tiene wheels para Python 3.12, no debería fallar |

**Verificar si el fallo es de uv o del sistema:**
```powershell
# Si falla con uv, probar con pip directamente
# Si pip también falla, el problema es del sistema, no de uv
uv venv test-env --seed
test-env\Scripts\activate
pip install --use-pep517 --no-cache sounddevice
```

**Para `sounddevice` en Windows** — necesita PortAudio.
La forma más simple es instalar desde un wheel precompilado:
```powershell
# En el pyproject.toml del robot no cambia nada
# uv intentará el wheel primero automáticamente
# Si falla, instalar Visual C++ Build Tools desde:
# https://visualstudio.microsoft.com/visual-cpp-build-tools/
```

**Si un paquete falla por versión de Python:**
```powershell
# Ver qué wheels existen para el paquete
# https://pypi.org/project/<paquete>/#files
# Buscar wheels con cp312 (CPython 3.12) y win_amd64
```

---

## Exportar dependencias para el Pi 5

```powershell
cd robot
uv export --no-dev -o requirements.txt
```

Genera `requirements.txt` limpio solo con dependencias del robot.

---

## uvx vs uv run

| Comando | Cuándo |
|---|---|
| `uvx ruff` | Ruff aislado, sin acceso al proyecto |
| `uv run ruff` | ✅ Correcto para lint — necesita ver el código |
| `uvx pytest` | ❌ Pytest necesita ver el código |
| `uv run pytest` | ✅ Correcto |

Regla: si la herramienta necesita leer tu código, `uv run`. Si solo necesitas
el binario para algo puntual, `uvx`.

---

## Reglas que no se rompen

- No tocar `.venv` manualmente.
- No editar `uv.lock` — solo uv lo modifica.
- No usar `pip install`. Siempre `uv add`.
- `uv.lock` va a git. `.venv` y `.env` no van a git.
- Dev dependencies van con `--group`. Nunca en `[project.dependencies]`.
- Config de uv solo en el `pyproject.toml` raíz.
- Cache y `.venv` en el mismo disco para máximo rendimiento.
