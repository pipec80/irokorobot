# OMNiBot 2000 — Estructura completa del repositorio GitHub

## Archivos raíz obligatorios

omnibot/
├── CLAUDE.md                 ← Reglas para Claude Code (ya creado)
├── README.md                 ← Documentación principal (en creación)
├── LICENSE                   ← Licencia del proyecto
├── .gitignore                ← Archivos a ignorar (uv lo genera parcialmente)
├── .env.example              ← Variables de entorno documentadas, sin valores reales
├── .pre-commit-config.yaml   ← Hooks de pre-commit
├── pyproject.toml            ← Workspace raíz + configuración de herramientas
└── uv.lock                   ← Lockfile (SÍ va a git)

## Archivos GitHub específicos

omnibot/
└── .github/
    ├── ISSUE_TEMPLATE/
    │   ├── bug_report.md       ← Template para reportar bugs
    │   └── feature_request.md  ← Template para pedir features
    ├── PULL_REQUEST_TEMPLATE.md ← Template para PRs
    └── workflows/
        └── ci.yml              ← GitHub Actions CI

## Documentación adicional

omnibot/
└── docs/
    ├── ARCHITECTURE.md        ← Diagrama y explicación de la arquitectura
    ├── SETUP.md               ← Guía de instalación detallada (ya creado)
    └── TOOLING.md             ← Stack de calidad de código (ya creado)

## Archivos de comunidad (opcionales pero recomendados)

omnibot/
├── CONTRIBUTING.md            ← Cómo contribuir al proyecto
├── CHANGELOG.md               ← Historial de cambios por versión
├── SECURITY.md                ← Cómo reportar vulnerabilidades
└── CODE_OF_CONDUCT.md         ← Código de conducta (si es público)

## Lo que NO va al repo (en .gitignore)

.env                           ← Secretos
.venv/                         ← Entorno virtual
__pycache__/                   ← Cache Python
*.pyc                          ← Bytecode compilado
.mypy_cache/                   ← Cache de mypy
.ruff_cache/                   ← Cache de ruff
*.onnx                         ← Modelos de Piper (pesados, van por separado)
*.gguf                         ← Modelos LLM locales
models/                        ← Carpeta de modelos descargados
dist/                          ← Builds
*.egg-info/
