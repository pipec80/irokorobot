# OMNiBot — Stack de Calidad de Código
> **Status:** Historical bootstrap note. It is preserved as project history,
> not as current installation, dependency, CI, or quality instruction.
> Start with [the Iroko technical documentation portal](../../README.md).

This note records earlier tool evaluation and cannot override the root `justfile`, `pyproject.toml`, CI workflow, or runtime instructions.

> Investigado desde fuentes actuales (2025-2026). Todo lo que aparece aquí
> tiene mantenimiento activo confirmado. Sin herramientas abandonadas.

---

## El stack completo de un vistazo

| Categoría | Herramienta | Quién la mantiene | Estado |
|---|---|---|---|
| Linter + Formatter | **Ruff** | Astral (mismos de uv) | ✅ Activo |
| Type checker | **mypy** | python/mypy org | ✅ Activo |
| Doc style | **Ruff (reglas D)** | Astral | ✅ incluido en Ruff |
| Pre-commit framework | **pre-commit** | pre-commit org | ✅ Activo |
| Pre-commit + uv | **pre-commit-uv** | plugin comunitario | ✅ Activo |
| Vulnerabilidades deps | **pip-audit** | PyPA + Trail of Bits + Google | ✅ Oficial |
| SAST (código) | **Bandit** | PyCQA | ⚠️ Activo pero envejeciendo |
| Paquetes desactualizados | **uv lock --upgrade** | Astral | ✅ Nativo en uv |
| CI/CD | **GitHub Actions + setup-uv** | Astral | ✅ Oficial |

---

## 1. Ruff — Linter y Formatter

Ruff reemplaza: Flake8, Black, isort, pydocstyle, pyupgrade, autoflake.
Todo en un solo binario escrito en Rust. Mismo equipo que uv.

**Por qué Ruff y no las alternativas:**
- Black está vivo pero Ruff lo reemplaza completamente. No tiene sentido tener ambos.
- Flake8 sigue funcionando pero es significativamente más lento y requiere plugins separados.
- isort se puede seguir usando pero Ruff incluye su funcionalidad con la regla `I`.
- pylint tiene análisis más profundo pero es lento y produce mucho ruido.

**Configuración en `pyproject.toml` raíz:**

```toml
[tool.ruff]
line-length = 88
target-version = "py312"
# Excluir archivos generados
exclude = [".venv", "__pycache__", "*.pyi"]

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "N",    # pep8-naming
    "UP",   # pyupgrade — moderniza sintaxis automáticamente
    "B",    # flake8-bugbear — bugs comunes
    "C4",   # flake8-comprehensions — mejores list/dict comprehensions
    "SIM",  # flake8-simplify
    "D",    # pydocstyle — doc strings
]
ignore = [
    "E501",   # line too long — lo maneja el formatter
    "D100",   # missing docstring in public module
    "D104",   # missing docstring in public package
]

[tool.ruff.lint.pydocstyle]
convention = "google"   # o "numpy" o "pep257"

[tool.ruff.lint.isort]
known-first-party = ["server", "robot"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

**Comandos:**
```powershell
uv run ruff check .          # lintear
uv run ruff check . --fix    # lintear y autofix
uv run ruff format .         # formatear
uv run ruff format . --check # verificar formato sin cambiar nada
```

---

## 2. mypy — Type Checker

Ruff no es un type checker. Detecta problemas de estilo y bugs comunes,
pero no verifica tipos. mypy hace eso.

**Por qué mypy y no la alternativa:**
Astral acaba de lanzar `ty` — su propio type checker en Rust, extremadamente
rápido. El problema: está en desarrollo activo, aún no es estable. Para un
proyecto nuevo que necesitas que funcione hoy, mypy es la decisión correcta.
Cuando `ty` madure (probablemente fin de 2025 - 2026), migrar será trivial.

**Configuración en `pyproject.toml` raíz:**

```toml
[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_any_generics = true
check_untyped_defs = true
no_implicit_reexport = true
warn_redundant_casts = true
warn_unused_ignores = true

# Ignorar librerías sin type stubs
[[tool.mypy.overrides]]
module = ["faster_whisper.*", "sounddevice.*", "piper.*"]
ignore_missing_imports = true
```

**Instalación:**
```powershell
uv add --group lint mypy
```

**Comando:**
```powershell
uv run mypy server/src robot/src
```

---

## 3. pip-audit — Vulnerabilidades en Dependencias

Herramienta oficial de PyPA. Escanea el entorno contra la base de datos
de vulnerabilidades de Python (PyPA Advisory Database). Mantenida con
apoyo de Trail of Bits y Google.

**Qué detecta:** CVEs en paquetes instalados. Si `fastapi 0.x.x` tiene
una vulnerabilidad conocida, pip-audit la reporta y te dice a qué versión
actualizar.

**Qué NO detecta:** código malicioso, problemas de lógica, seguridad del
código propio. Para eso está Bandit.

**Instalación:**
```powershell
uv add --group security pip-audit
```

**Comando:**
```powershell
# Auditar el entorno completo
uv run pip-audit

# Solo dependencias locales (ignora paquetes del sistema)
uv run pip-audit --local

# Fix automático cuando sea posible
uv run pip-audit --fix

# Output JSON para CI
uv run pip-audit --format json
```

---

## 4. Bandit — SAST (Seguridad en el Código)

Analiza el código fuente buscando patrones inseguros: eval(), subprocess
sin sanitizar, hashlib con algoritmos débiles, credenciales hardcodeadas, etc.

**Estado honesto:** Bandit funciona y está mantenido por PyCQA. Algunos
artículos de 2025 cuestionan si sigue siendo la mejor opción para Python
moderno. Para este proyecto (robot doméstico, no exposición pública) es
suficiente y no agrega fricción innecesaria.

**Instalación:**
```powershell
uv add --group security bandit
```

**Configuración en `pyproject.toml`:**
```toml
[tool.bandit]
targets = ["server/src", "robot/src"]
severity = "MEDIUM"
confidence = "HIGH"
skips = ["B101"]  # skip assert_used — común en tests
```

**Comando:**
```powershell
uv run bandit -r server/src robot/src -ll
```

---

## 5. Pre-commit

Framework que instala hooks de git. Corre automáticamente antes de cada
commit. Si algo falla, el commit no pasa.

**Instalación via uv (con plugin de velocidad):**
```powershell
uv tool install pre-commit --with pre-commit-uv
```

`pre-commit-uv` parchea pre-commit para usar uv al instalar los entornos
de los hooks — instalación de hooks 30% más rápida.

**Instalar los hooks en el repo:**
```powershell
pre-commit install
```

**Archivo `.pre-commit-config.yaml` en la raíz:**

```yaml
default_language_version:
  python: python3.12

repos:
  # Checks básicos de archivos
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-merge-conflict
      - id: check-added-large-files
      - id: debug-statements      # detecta print() y breakpoint() olvidados

  # uv — verificar que el lockfile esté actualizado
  - repo: https://github.com/astral-sh/uv-pre-commit
    rev: 0.11.7    # actualizar a la versión de uv que uses
    hooks:
      - id: uv-lock

  # Ruff — linter y formatter
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.9    # mantener sincronizado con pyproject.toml
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  # Bandit — SAST
  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.9
    hooks:
      - id: bandit
        args: ["-r", "-ll", "--severity-level", "MEDIUM"]
        exclude: ^tests/
```

**⚠️ Problema de version drift:**
Cuando actualizas ruff en `pyproject.toml`, también debes actualizar el
`rev` en `.pre-commit-config.yaml` manualmente. Si no lo haces, los
hooks corren versiones distintas a las del proyecto.

Solución: usar `sync-with-uv` (opcional, agrega un hook que sincroniza
automáticamente) o simplemente recordar actualizar ambos archivos juntos.

**Comandos:**
```powershell
# Correr todos los hooks sobre todos los archivos
pre-commit run --all-files

# Correr un hook específico
pre-commit run ruff --all-files

# Actualizar versiones de los hooks
pre-commit autoupdate

# Desinstalar hooks
pre-commit uninstall
```

---

## 6. Paquetes desactualizados

Con uv esto es nativo. No necesitas una herramienta separada como
`pip-check-updates` o `outdated`.

```powershell
# Ver el árbol completo con versiones
uv tree

# Actualizar todos los paquetes (respeta constraints del pyproject.toml)
uv lock --upgrade

# Actualizar un paquete específico
uv lock --upgrade-package fastapi

# Después de actualizar el lock, sincronizar el entorno
uv sync
```

---

## 7. Dependency groups — cómo queda todo

Todos los grupos de desarrollo van en el `pyproject.toml` raíz:

```toml
[dependency-groups]
lint = [
    "ruff>=0.9.0",
    "mypy>=1.13.0",
]
security = [
    "pip-audit>=2.9.0",
    "bandit>=1.7.9",
]
dev = [
    {include-group = "lint"},
    {include-group = "security"},
    "pre-commit>=4.0.0",
]
```

Instalar todo:
```powershell
uv add --group lint ruff mypy
uv add --group security pip-audit bandit
uv add --group dev pre-commit
uv sync --all-groups
```

---

## 8. CI/CD — GitHub Actions

Archivo `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true

      - name: Sync dependencies
        run: uv sync --all-groups

      - name: Lint
        run: uv run ruff check .

      - name: Format check
        run: uv run ruff format --check .

      - name: Type check
        run: uv run mypy server/src robot/src

      - name: Security audit
        run: uv run pip-audit --local

      - name: SAST
        run: uv run bandit -r server/src robot/src -ll
```

---

## El orden de prioridad para implementar

No todo de golpe. En orden lógico:

1. **Ruff** — primero. Máximo beneficio, mínimo setup.
2. **pre-commit** — inmediatamente después. Automatiza que ruff corra.
3. **mypy** — antes de escribir código de producción. Cuesta más setup
   inicial pero vale la pena.
4. **pip-audit** — al tener dependencias reales agregadas.
5. **Bandit** — antes de exponer cualquier endpoint al exterior.
6. **CI/CD** — cuando el proyecto tenga su repositorio en GitHub.

---

## Lo que decidí NO incluir y por qué

| Herramienta | Razón |
|---|---|
| Black | Ruff lo reemplaza completamente |
| isort | Ruff incluye isort con regla `I` |
| Flake8 | Ruff lo reemplaza con 800+ reglas |
| pylint | Lento, mucho ruido, Ruff cubre lo importante |
| safety | `pip-audit` es el reemplazo oficial mantenido por PyPA |
| ty (Astral) | Muy nuevo, aún inestable. Revisitar en 2026 |
| commitizen | Útil para proyectos con releases semánticos. Overkill aquí. |
