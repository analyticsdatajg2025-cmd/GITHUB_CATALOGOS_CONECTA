# GITHUB_CATALOGOS_CONECTA
Automatizar diseños como Story, PPL y Display para conecta (EFE y LC).

> **Flyers desactivados desde 2026-11-09.** El código de flyers quedó comentado en `main.py`
> y en los programas clásicos; las filas FLYER del Sheet se ignoran.

## Cómo se generan las piezas
1. Comercial llena **Hoja 1** del Sheet. La columna «Tipo de diseño» es la campaña.
2. GitHub → **Actions → Catalogo Conecta Automation → Run workflow** (o desde el Calibrador, más adelante).
   Opciones, todas opcionales:
   - **Tiendas**: LC y EFE, solo LC o solo EFE (las dos salen en la misma corrida).
   - **Diseño LC / Diseño EFE**: qué diseño usar. Vacío = el que se llama igual que la campaña.
   - **Formatos**, **SKUs**, **Marcas**: separados por coma, para rehacer solo eso.
   - **Solo lo que falta**: no rehace lo que ya existe. Sin marcarlo, todo lo elegido se vuelve a dibujar.
   - **Programa**: «Clásico LC» / «Clásico EFE» corren los diseños clásicos de siempre.
3. Las piezas quedan en:
   - `output/<TIENDA>/<SKU>/<SKU>_<FORMATO>.jpg` (PPL, STORY, DISPLAY)
   - ~~`output/<TIENDA>/FLYER/<ID_Flyer>.jpg`~~ (flyers desactivados)
   y su link en la hoja **Resultados** (si la pieza ya tenía fila, se actualiza esa misma fila).
4. **Cada corrida borra el material antiguo de `output/`** (programa «Nuevo»; se borra al final, cuando
   las piezas nuevas ya están hechas y anotadas):
   - Corrida completa (las dos tiendas, todos los formatos, sin SKUs ni marcas, sin «solo lo que falta»):
     `output/` queda solo con las piezas de esa corrida.
   - Corrida parcial (una tienda, algunos formatos, SKUs o marcas, o «solo lo que falta»): de las tiendas
     elegidas se borra lo que ya no está en el Sheet y se quitan sus filas de **Resultados**. Las piezas
     vigentes que no se rehicieron se quedan, porque su link sigue en uso.
   - Los programas clásicos no borran nada.

## Dónde está cada cosa
| Qué | Dónde |
|---|---|
| Diseños (coordenadas del Calibrador) | `DISENOS/<TIENDA>/<nombre>.json`, uno por diseño, con nombre y comentario |
| Fondos de cada campaña | `FONDOS/<TIENDA>/<campaña>/<TIENDA> - <campaña> - <FORMATO>.jpg` |
| Botones e imágenes de un diseño | en la carpeta de fondos de la campaña, o en `FONDOS/<TIENDA>/` para compartirlos |
| Tipografías | `TIPOGRAFIA/<TIENDA>/` |
| Programa | `main.py` (orquesta), `motor_lc.py` y `motor_efe.py` (dibujan cada tienda) |
| Diseños clásicos | `DISEÑO_LC_CLASICO.txt`, `DISEÑO_EFE_CLASICO.txt` (se corren con la opción «Programa») |

Ya no se pega nada en `main.py` ni se edita `FORZAR_REGENERAR`.
