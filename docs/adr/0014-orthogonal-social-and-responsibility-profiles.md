# ADR 0014: Perfiles sociales y de responsabilidad ortogonales

- Estado: Aceptado
- Fecha: 2026-09-04
- Decisores: Pipec
- Amplía: [ADR 0006](0006-personal-and-family-companion-profiles.md)

## Contexto

Iroko ya distingue dos perfiles sociales, `personal` y `family`. Esa decisión
define quién convive con el sistema y cómo se protege la información entre
personas, pero no expresa qué responsabilidad está autorizado a asumir Iroko.

La visión de producto también contempla acompañamiento, cuidado y educación.
Modelar esas responsabilidades como nuevos productos o cerebros independientes
duplicaría identidad, memoria, autorización y conversación. Modelarlas como una
sola escala de privilegios permitiría, en cambio, que un propietario técnico
heredara autoridad clínica, educativa o sobre los datos privados de otro adulto.

El código vigente solo demuestra capacidades de acompañamiento. No existe aún
un pipeline funcional y validado de sensores, decisiones clínicas, acciones,
resultados y feedback que justifique presentar a Iroko como enfermero 24/7 o
como educador autónomo.

## Decisión

Iroko conserva una sola arquitectura cognitiva y expresa su configuración con
dos ejes independientes:

```text
Perfil social
├── personal
└── family

Responsabilidad
├── companion
├── care
└── education
```

El perfil social responde quiénes participan y qué límites existen entre sus
datos:

- `personal`: una persona principal administra sus propios datos y la
  configuración permitida;
- `family`: varias personas identificadas comparten capacidades domésticas,
  sin que el administrador obtenga automáticamente los datos privados de otros
  adultos.

El perfil de responsabilidad responde qué clase de capacidades puede ejercer
Iroko:

- `companion`: conversación, compañía y asistencia doméstica no clínica;
- `care`: capacidades futuras de cuidado, cada una limitada por políticas,
  evidencia y criterios de aceptación propios;
- `education`: capacidades futuras de apoyo educativo, también limitadas por
  políticas, evidencia y criterios de aceptación propios.

Solo `companion` está activo como objetivo de entrega. `care` y `education` son
direcciones futuras, no modos implementados ni promesas de producto.

Ambos ejes comparten el mismo controlador, identidad, memoria y evaluador de
políticas. Las diferencias se expresarán mediante capacidades explícitas y no
mediante bifurcaciones completas de la arquitectura.

En escenarios de cuidado pueden existir, entre otros, beneficiario, familiar,
cuidador, profesional de salud, administrador técnico y contacto de emergencia.
En educación pueden existir estudiante, tutor y educador. Ningún rol hereda por
su nombre autoridad general sobre otro actor o sus datos.

Una identidad resuelta sigue sin constituir autorización. Una persona
desconocida puede mantener conversación general, pero no leer memoria protegida
ni activar capacidades sensibles. Cara y voz siguen siendo evidencia de
identidad, nunca una concesión automática de permisos.

Esta decisión es conceptual. No autoriza todavía nuevos enums, tablas, rutas,
configuración ni comportamiento de runtime. Cada incremento ejecutable deberá
tener un plan `Ready`, política tipada y aceptación observable.

## Consecuencias

### Positivas

- Permite combinar, por ejemplo, `personal + companion` o `family + care` sin
  crear cerebros paralelos.
- Mantiene una frontera clara entre convivencia social y responsabilidad.
- Evita que `owner`, administrador o familiar se conviertan en permisos
  universales.
- Permite cerrar primero el compañero personal y añadir responsabilidades solo
  cuando estén demostradas.

### Costes

- La matriz de políticas y pruebas crecerá al añadir responsabilidades.
- Cada capacidad sensible deberá definir actor, propósito, procedencia,
  consentimiento, retención y auditoría.
- La comunicación de producto deberá distinguir una dirección futura de una
  capacidad aceptada.

## Alternativas descartadas

### Un producto o cerebro por combinación

Descartado porque duplicaría el núcleo cognitivo y favorecería divergencias de
identidad, memoria y privacidad.

### Un único modo con permisos acumulativos

Descartado porque mezcla relación social y autoridad, y facilita escaladas de
privilegios implícitas.

### Implementar ahora `care` y `education`

Descartado porque no existe evidencia de runtime, seguridad ni aceptación que
sostenga esas responsabilidades.

## Revisión

Revisar esta decisión antes de activar la primera capacidad `care` o
`education`, o si una combinación demuestra necesitar una frontera de runtime
distinta. Cualquier reemplazo requiere un ADR nuevo.
