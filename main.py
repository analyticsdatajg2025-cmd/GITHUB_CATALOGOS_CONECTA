import os
from datetime import datetime, timedelta
# Importamos tus archivos como módulos
# Asumimos que los renombraste a diseno_lc.py y diseno_efe.py
import diseno_lc as lc
import diseno_efe as efe

def ejecutar_sistema_unificado():
    os.makedirs('output', exist_ok=True)
    # Obtención de hora actual (Lima UTC-5)
    h_lima = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")
    archivos_generados = 0

    print("--- INICIANDO PROCESAMIENTO UNIFICADO (LC & EFE) ---")

    # --- 1. PROCESAMIENTO TIENDA: LC ---
    print("\n🔎 Procesando Tienda: LC...")
    try:
        data_lc, res_sheet_lc, viejos_lc = lc.get_sheets_data()
        
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
                        # Enviamos las 7 columnas: Tienda es "LC" [cite: 55]
                        res_sheet_lc.append_row([h_lima, llave, "LC", row['Tipo de diseño'], f_v, c, url])
                        archivos_generados += 1

        # Flyers LC
        fly_g_lc = data_lc[data_lc['Formato'].astype(str).str.upper().str.strip() == "FLYER"]
        for id_f, group in fly_g_lc.groupby('ID_Flyer'):
            if str(id_f) in ["0", "0.0", ""]: continue
            llave = f"{id_f}_FLYER_AMARILLO".upper()
            if llave not in viejos_lc:
                url = lc.generar_diseno(group, "AMARILLO")
                if url:
                    # Enviamos las 7 columnas [cite: 57]
                    res_sheet_lc.append_row([h_lima, llave, "LC", group.iloc[0]['Tipo de diseño'], "FLYER", "AMARILLO", url])
                    archivos_generados += 1
    except Exception as error:
        print(f"❌ Error en módulo LC: {error}")

    # --- 2. PROCESAMIENTO TIENDA: EFE ---
    print("\n🔎 Procesando Tienda: EFE...")
    try:
        data_efe, res_sheet_efe, viejos_efe = efe.get_sheets_data()
        
        # Productos Individuales EFE
        for idx, row in data_efe.iterrows():
            f_v = str(row['Formato']).upper().strip()
            if f_v in ["FLYER", "", "0"]: continue
            tienda = str(row.get('Tienda', 'EFE')).strip().upper() # Valor por defecto EFE [cite: 144]
            llave = f"{row['SKU']}_{f_v}_{tienda}_EFE".upper()
            
            if llave not in viejos_efe:
                url = efe.generar_diseno(row)
                if url:
                    # EFE ya enviaba 7 columnas por su lógica interna [cite: 144]
                    res_sheet_efe.append_row([h_lima, llave, tienda, row['Tipo de diseño'], f_v, "EFE", url])
                    archivos_generados += 1

        # Flyers EFE
        fly_g_efe = data_efe[data_efe['Formato'].astype(str).str.upper().str.strip() == "FLYER"]
        for id_f, group in fly_g_efe.groupby('ID_Flyer'):
            if str(id_f) in ["0", "0.0", ""]: continue
            llave = f"{id_f}_FLYER_EFE".upper()
            if llave not in viejos_efe:
                url = efe.generar_diseno(group)
                if url:
                    # Enviamos las 7 columnas para EFE [cite: 145]
                    res_sheet_efe.append_row([h_lima, llave, "EFE", group.iloc[0]['Tipo de diseño'], "FLYER", "EFE", url])
                    archivos_generados += 1
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
    