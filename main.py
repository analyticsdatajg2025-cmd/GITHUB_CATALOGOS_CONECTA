import os
from datetime import datetime, timedelta
import diseno_lc as lc
import diseno_efe as efe

def ejecutar_sistema_unificado():
    os.makedirs('output', exist_ok=True)
    h_lima = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")
    archivos_generados = 0

    print("--- INICIANDO PROCESAMIENTO UNIFICADO (LC & EFE) ---")

    # --- 1. PROCESAMIENTO TIENDA: LC ---
    print("\n🔎 Procesando Tienda: LC...")
    try:
        data_lc, res_sheet_lc, viejos_lc = lc.get_sheets_data()
        filas_para_log_lc = [] # <-- Lista para acumular resultados de LC

        # Productos Individuales LC
        for idx, row in data_lc.iterrows():
            f_v = str(row['Formato']).upper().strip()
            if f_v in ["FLYER", "", "0"]: continue
            
            versiones = ["AMARILLO", "AZUL"] if str(row['Tipo de diseño']).strip() == "DSCTOS POWER" else ["AMARILLO"]
            for c in versiones:
                llave = f"{row['SKU']}_{f_v}_{c}".upper()
                if llave not in viejos_lc:
                    url = lc.generar_diseno(row, c)
                    if url:
                        # En lugar de append_row, guardamos en la lista [cite: 55]
                        filas_para_log_lc.append([h_lima, llave, "LC", row['Tipo de diseño'], f_v, c, url])
                        archivos_generados += 1

        # Flyers LC
        fly_g_lc = data_lc[data_lc['Formato'].astype(str).str.upper().str.strip() == "FLYER"]
        for id_f, group in fly_g_lc.groupby('ID_Flyer'):
            if str(id_f) in ["0", "0.0", ""]: continue
            llave = f"{id_f}_FLYER_AMARILLO".upper()
            if llave not in viejos_lc:
                url = lc.generar_diseno(group, "AMARILLO")
                if url:
                    # Guardamos en la lista [cite: 57]
                    filas_para_log_lc.append([h_lima, llave, "LC", group.iloc[0]['Tipo de diseño'], "FLYER", "AMARILLO", url])
                    archivos_generados += 1
        
        # --- ESCRITURA ÚNICA PARA LC ---
        if filas_para_log_lc:
            res_sheet_lc.append_rows(filas_para_log_lc) # Envía todo de golpe
            print(f"✅ Se registraron {len(filas_para_log_lc)} filas en LC.")

    except Exception as error:
        print(f"❌ Error en módulo LC: {error}")

    # --- 2. PROCESAMIENTO TIENDA: EFE ---
    print("\n🔎 Procesando Tienda: EFE...")
    try:
        data_efe, res_sheet_efe, viejos_efe = efe.get_sheets_data()
        filas_para_log_efe = [] # <-- Lista para acumular resultados de EFE
        
        # Productos Individuales EFE
        for idx, row in data_efe.iterrows():
            f_v = str(row['Formato']).upper().strip()
            if f_v in ["FLYER", "", "0"]: continue
            tienda = str(row.get('Tienda', 'EFE')).strip().upper() [cite: 144]
            llave = f"{row['SKU']}_{f_v}_{tienda}_EFE".upper()
            
            if llave not in viejos_efe:
                url = efe.generar_diseno(row)
                if url:
                    # Guardamos en la lista [cite: 144]
                    filas_para_log_efe.append([h_lima, llave, tienda, row['Tipo de diseño'], f_v, "EFE", url])
                    archivos_generados += 1

        # Flyers EFE
        fly_g_efe = data_efe[data_efe['Formato'].astype(str).str.upper().str.strip() == "FLYER"]
        for id_f, group in fly_g_efe.groupby('ID_Flyer'):
            if str(id_f) in ["0", "0.0", ""]: continue
            llave = f"{id_f}_FLYER_EFE".upper()
            if llave not in viejos_efe:
                url = efe.generar_diseno(group)
                if url:
                    # Guardamos en la lista [cite: 145]
                    filas_para_log_efe.append([h_lima, llave, "EFE", group.iloc[0]['Tipo de diseño'], "FLYER", "EFE", url])
                    archivos_generados += 1

        # --- ESCRITURA ÚNICA PARA EFE ---
        if filas_para_log_efe:
            res_sheet_efe.append_rows(filas_para_log_efe) # Envía todo de golpe
            print(f"✅ Se registraron {len(filas_para_log_efe)} filas en EFE.")

    except Exception as error:
        print(f"❌ Error en módulo EFE: {error}")

    # --- CIERRE DE SEGURIDAD ---
    if archivos_generados == 0:
        print("⚠️ No se generaron piezas nuevas en ninguna tienda.")
        with open("output/placeholder.txt", "w") as f:
            f.write(f"Ejecución unificada sin cambios: {h_lima}")
    else:
        print(f"✅ Éxito total: Se crearon {archivos_generados} archivos nuevos.")

if __name__ == "__main__":
    ejecutar_sistema_unificado()