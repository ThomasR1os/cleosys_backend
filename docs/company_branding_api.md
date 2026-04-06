# Contrato API: branding de compañía (PDF / cotizaciones)

## Lectura

En cualquier respuesta que incluya `Company` serializado (`GET /api/companies/`, `GET /api/companies/{id}/`, `profile.company` en `/api/auth/me/`, etc.), el objeto incluye la clave **`branding`** (objeto JSON).

Si no existe fila en `company_branding` para esa compañía, `branding` sigue presente con los **valores por defecto** documentados abajo (misma forma que cuando hay fila).

### Forma de `branding`

| Campo           | Tipo   | Descripción |
|-----------------|--------|-------------|
| `primary`       | string | Hex `#RRGGBB` (mayúsculas tras guardar). Títulos, cabecera de tabla, acentos. |
| `primary_light` | string | Fondos suaves (resumen / totales). |
| `muted`         | string | Texto secundario / etiquetas. |
| `border`        | string | Bordes y líneas. |
| `table_stripe`  | string | Rayado de filas de productos. |
| `emphasis_bar`  | string | Barra oscura de totales. |
| `text_body`     | string | Párrafos (ej. cuentas bancarias). |
| `text_label`    | string | Etiquetas destacadas. |
| `text_caption`  | string | Texto secundario / cursivas. |
| `extensions`    | object | Diccionario JSON opcional para extensiones futuras (v1: suele ser `{}`). |

### Defaults (cuando no hay fila DB)

Coinciden con la paleta fija actual del PDF de cotizaciones:

- `primary`: `#1E3A5F`
- `primary_light`: `#F1F5F9`
- `muted`: `#64748B`
- `border`: `#E2E8F0`
- `table_stripe`: `#F8FAFC`
- `emphasis_bar`: `#0F172A`
- `text_body`: `#3C3C3C`
- `text_label`: `#374151`
- `text_caption`: `#475569`
- `extensions`: `{}`

## Escritura

- **`PATCH /api/companies/{id}/branding/`**  
  Cuerpo JSON parcial con cualquiera de los campos anteriores (excepto que no hace falta enviar todos los colores).  
  Permisos: mismo criterio que otros endpoints de administración (`AdminAccessPermission`: rol ADMIN en perfil o superusuario).

Al primer PATCH exitoso se **crea** la fila `CompanyBranding` para esa compañía si no existía.

### Validación

- Colores: exactamente **6 dígitos hexadecimales**, con `#` opcional en entrada; en respuestas y persistencia se normaliza a **`#` + mayúsculas**.
- `extensions`: debe ser objeto JSON (no un array ni escalar).

El contraste de colores no se valida en backend (puede hacerse en frontend).

## Django admin

`Company` tiene un inline de branding; también existe el modelo `CompanyBranding` registrado por separado.
