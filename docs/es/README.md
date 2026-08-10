# Documentación técnica de Iroko

> Estado: Portal de documentación. No es un plan de implementación.

## Empieza aquí

Comienza con el [perfil público de Iroko](../product/iroko-profile.md), y usa después el [índice de arquitectura canónico](../architecture/README.md) y su [estado actual](../architecture/current-state.md) para distinguir evidencia de intención futura. La guía reproducible de configuración de audio se entrega en el Slice 2.

## Elige tu ruta

| Lector | Comienza con | Luego usa |
| --- | --- | --- |
| Visitante | [Perfil de Iroko](../product/iroko-profile.md) | [Bienvenida en español](../../README.es.md) |
| Desarrollador nuevo | [Bienvenida en español](../../README.es.md) | [Índice de arquitectura](../architecture/README.md) y [estado actual](../architecture/current-state.md) |
| Colaborador | [Estado actual](../architecture/current-state.md) | [Hoja de ruta cognitiva](../roadmap/cognitive-roadmap.md) e [índice de planes](../plans/README.md) |
| Codex/arquitecto | [Índice de arquitectura](../architecture/README.md) | [Estado actual](../architecture/current-state.md), [hoja de ruta](../roadmap/cognitive-roadmap.md) y [planes](../plans/README.md) |
| Mantenedor/publicador | [AGENTS.md](../../AGENTS.md) | [justfile](../../justfile), [estado actual](../architecture/current-state.md) e [índice de planes](../plans/README.md) |

## Qué está implementado hoy

**Implemented:** el [estado actual](../architecture/current-state.md) es el registro respaldado por evidencia del comportamiento disponible en el repositorio actual. No deduzcas soporte adicional de runtime, proveedores o hardware a partir de este portal.

## Autoridad canónica

El inglés es la fuente técnica canónica; esta página en español es su equivalente mantenido. El [índice de arquitectura](../architecture/README.md), el [estado actual](../architecture/current-state.md), la [hoja de ruta cognitiva](../roadmap/cognitive-roadmap.md) y el [índice de planes](../plans/README.md) gobiernan la dirección técnica actual.

## Procedencia de la documentación

La [hoja de ruta preelectrónica](../architecture/roadmap-cerebro-agnostico-pre-electronica.md) y la [auditoría de fundamentos cognitivos](../architecture/cognitive-foundation-audit.md) son contexto histórico, no planes ejecutables. M3/M4 son contexto histórico; M4 está implementado con cierre histórico no demostrado. El trabajo nuevo sigue el índice de arquitectura canónico, el estado actual, la hoja de ruta cognitiva y el [plan actual nombrado](../plans/0007-iroko-documentation-manual.md).

## Etiquetas de estado de la documentación

- **Implemented** significa comportamiento verificado en código, una prueba o el [estado actual](../architecture/current-state.md).
- **Planned** significa intención futura enlazada a la [hoja de ruta](../roadmap/cognitive-roadmap.md) o a un [plan](../plans/README.md).
- **Historical** significa contexto preservado, no guía operativa actual.

## Límite del alcance actual

Este portal documenta una experiencia de desarrollo en PC. Raspberry Pi, homelab, OMNiBot 2000, electrónica, acción física y procedimientos de despliegue siguen siendo visión futura y no procedimientos operativos compatibles. La acción autónoma y la escalada operativa a la nube no están implementadas.
