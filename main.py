# Genera las piezas de LC y EFE en una sola corrida.
#
# Ya no se pega nada aqui. Las coordenadas viven en DISENOS/<TIENDA>/<nombre>.json
# (las guarda el Calibrador) y el dibujo de cada tienda en motor_lc.py y motor_efe.py.
#
# Opciones (las llena el workflow "Catalogo Conecta Automation" al darle Run workflow;
# vacias = todo):
#   TIENDAS         LC, EFE o las dos (por defecto las dos)
#   DISENO_LC       nombre del diseño a usar en LC   (vacio = el que se llama igual que la campaña)
#   DISENO_EFE      nombre del diseño a usar en EFE  (idem)
#   FORMATOS        PPL, STORY, DISPLAY separados por coma
#                   (FLYER desactivado desde 2026-11-09: ya no hay flyers)
#   SKUS            SKUs separados por coma
#   MARCAS          marcas separadas por coma
#   SOLO_FALTANTES  "true" = salta lo que ya esta en Resultados y en output/.
#                   Por defecto todo lo elegido se vuelve a dibujar.
import os
import re
import sys
from datetime import datetime, timedelta

import motor_lc
import motor_efe

MOTORES = {"LC": motor_lc, "EFE": motor_efe}


def opcion_lista(nombre):
    """Lista en MAYUSCULAS. Se separa por coma, punto y coma o salto de linea
    (no por espacio: hay SKUs con espacios, como 'CX 505 PLUS')."""
    return [x.strip().upper() for x in re.split(r"[,;\n]+", os.environ.get(nombre, "")) if x.strip()]


def opcion_si(nombre):
    return os.environ.get(nombre, "").strip().lower() in ("true", "1", "si", "sí", "yes")


TIENDAS = [t for t in (opcion_lista("TIENDAS") or ["LC", "EFE"]) if t in MOTORES]
DISENOS = {"LC": os.environ.get("DISENO_LC", "").strip(), "EFE": os.environ.get("DISENO_EFE", "").strip()}
FORMATOS = opcion_lista("FORMATOS")
SKUS = opcion_lista("SKUS")
MARCAS = opcion_lista("MARCAS")
SOLO_FALTANTES = opcion_si("SOLO_FALTANTES")


def limpio(valor):
    return str(valor).replace("/", "-").replace("\\", "-")


# Cada tienda conserva sus llaves de siempre en 'Resultados', para que las filas
# viejas se sigan encontrando y se actualicen en vez de duplicarse.
def llave_pieza(tienda, sku, formato):
    if tienda == "LC":
        return f"{limpio(sku)}_{formato}_AMARILLO".upper()
    return f"{limpio(sku)}_{formato}_{tienda}_EFE".upper()


# FLYERS DESACTIVADOS (2026-11-09): ya no hay flyers. Se deja comentado por si vuelven.
# def llave_flyer(tienda, id_flyer):
#     if tienda == "LC":
#         return f"{id_flyer}_FLYER_AMARILLO".upper()
#     return f"{limpio(id_flyer)}_FLYER_EFE".upper()


COLOR = {"LC": "AMARILLO", "EFE": "EFE"}


def generar(tienda, data_input):
    if tienda == "LC":
        return motor_lc.generar_diseno(data_input, "AMARILLO")
    return motor_efe.generar_diseno(data_input)


def coincide(fila):
    if SKUS and str(fila.get("SKU", "")).strip().upper() not in SKUS:
        return False
    if MARCAS and str(fila.get("Marca", "")).strip().upper() not in MARCAS:
        return False
    return True


def main():
    print(f"Opciones -> tiendas: {TIENDAS} | diseños: {DISENOS} | formatos: {FORMATOS or 'todos'} | "
          f"SKUs: {SKUS or 'todos'} | marcas: {MARCAS or 'todas'} | solo faltantes: {SOLO_FALTANTES}")

    # Un diseño elegido que no existe es un error: mejor parar que dibujar con otro.
    for t in TIENDAS:
        nombre = DISENOS[t]
        if nombre and nombre.upper() not in MOTORES[t].LAYOUTS:
            print(f"❌ No existe el diseño '{nombre}' en DISENOS/{t}/. "
                  f"Hay: {sorted(MOTORES[t].LAYOUTS) or 'ninguno'}")
            sys.exit(1)

    data, res_sheet, viejos = motor_lc.get_sheets_data()
    h_lima = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")
    filas_nuevas, filas_actualizar, errores = [], [], []
    hechas = 0

    def hay_que_generar(llave, archivo):
        if not SOLO_FALTANTES:
            return True
        return llave not in viejos or not os.path.exists(os.path.join("output", archivo))

    def registrar(tienda, motor, llave, diseno, formato, url, sku_link):
        lw = motor.link_web(tienda, sku_link)
        fila = [h_lima, llave, tienda, diseno, formato, COLOR[tienda], url, lw]
        if viejos.get(llave):
            filas_actualizar.append((viejos[llave], fila))
        elif llave not in viejos:
            filas_nuevas.append(fila)
            viejos[llave] = None  # evita duplicar si se repite en la misma corrida

    def dibujar(tienda, motor, llave, data_input, diseno, formato, sku_link):
        nonlocal hechas
        try:
            url = generar(tienda, data_input)
        except Exception as e:
            print(f"❌ {llave}: {e}")
            errores.append(f"{llave}: {e}")
            return
        if not url:
            errores.append(f"{llave}: no se genero (revisa el aviso de arriba, por ejemplo un fondo que falta)")
            return
        registrar(tienda, motor, llave, diseno, formato, url, sku_link)
        hechas += 1

    os.makedirs("output", exist_ok=True)
    for tienda in TIENDAS:
        motor = MOTORES[tienda]
        motor.DISENO_FORZADO = DISENOS[tienda]
        d = data[data["Tienda"].astype(str).str.strip().str.upper() == tienda].reset_index(drop=True)
        formato_col = d["Formato"].astype(str).str.upper().str.strip()
        print(f"\n===== {tienda}: {len(d)} filas en el Sheet" +
              (f" | diseño elegido: {DISENOS[tienda]}" if DISENOS[tienda] else ""))

        # Piezas individuales (PPL, STORY, DISPLAY). Las filas FLYER se ignoran.
        for _, row in d[~formato_col.isin(["FLYER", "", "0"])].iterrows():
            f_v = str(row["Formato"]).upper().strip()
            if (FORMATOS and f_v not in FORMATOS) or not coincide(row):
                continue
            llave = llave_pieza(tienda, row["SKU"], f_v)
            if not hay_que_generar(llave, motor.ruta_salida(tienda, row)):
                continue
            print(f"🎨 {llave}")
            dibujar(tienda, motor, llave, row, row["Tipo de diseño"], f_v, row["SKU"])

        # FLYERS DESACTIVADOS (2026-11-09): ya no hay flyers. Las filas con Formato FLYER
        # del Sheet se ignoran (arriba se excluyen). Para reactivarlos, descomentar este bloque
        # y llave_flyer().
        # if FORMATOS and "FLYER" not in FORMATOS:
        #     continue
        # for id_f, grupo in d[formato_col == "FLYER"].groupby("ID_Flyer"):
        #     if str(id_f) in ("0", "0.0", ""):
        #         continue
        #     if (SKUS or MARCAS) and not any(coincide(r) for _, r in grupo.iterrows()):
        #         continue
        #     llave = llave_flyer(tienda, id_f)
        #     if not hay_que_generar(llave, motor.ruta_salida(tienda, grupo)):
        #         continue
        #     print(f"🎨 Flyer {llave}")
        #     sku_link = grupo.iloc[0]["SKU"] if motor.FLYER_USA_PRIMER_SKU else None
        #     dibujar(tienda, motor, llave, grupo, grupo.iloc[0]["Tipo de diseño"], "FLYER", sku_link)

    # Resultados: 1 peticion para las nuevas y 1 para las que ya estaban (misma fila, link nuevo)
    if filas_nuevas:
        res_sheet.append_rows(filas_nuevas)
    if filas_actualizar:
        res_sheet.batch_update([{"range": f"A{n}:H{n}", "values": [fila]} for n, fila in filas_actualizar])

    resumen = (f"Piezas generadas: {hechas} | filas nuevas en Resultados: {len(filas_nuevas)} | "
               f"filas actualizadas: {len(filas_actualizar)} | errores: {len(errores)}")
    print("\n" + ("✅ " if not errores else "⚠️  ") + resumen)
    for e in errores:
        print("   ❌ " + e)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(f"### Catalogo Conecta\n\n{resumen}\n\n" + "".join(f"- ❌ {e}\n" for e in errores))
    with open("last_run.txt", "w", encoding="utf-8") as fh:
        fh.write(f"{h_lima} | {resumen}\n")
    # Con errores la corrida queda en rojo, pero las piezas que si salieron se suben igual.
    if errores:
        sys.exit(1)


if __name__ == "__main__":
    main()
