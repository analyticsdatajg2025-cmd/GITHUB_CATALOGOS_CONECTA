import os
import json
import requests
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from io import BytesIO

# --- CONFIGURACIÓN DE RUTAS Y LINKS ---
USER_GH = "analyticsdatajg2025-cmd"
REPO_GH = "GITHUB_CATALOGOS_CONECTA"
RAW_URL = f"https://raw.githubusercontent.com/{USER_GH}/{REPO_GH}/main/output/"

# --- CONEXIÓN A GOOGLE SHEETS ---
def get_sheets_data():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # CAMBIO AQUÍ: Ahora lee 'GOOGLE_CREDENTIALS'
    creds_info = json.loads(os.environ.get('GOOGLE_CREDENTIALS'))
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key("1PmvCyC3d0VvvZSdvWM73NYusrYevVYtRzVs2gbxjw1M")
    
    data = pd.DataFrame(sheet.worksheet("Hoja 1").get_all_records())
    try:
        res_sheet = sheet.worksheet("Resultados")
    except:
        res_sheet = sheet.add_worksheet(title="Resultados", rows="1000", cols="10")
        res_sheet.append_row(["Fecha", "ID", "Diseño", "Formato", "Color", "Link"])
    
    return data, res_sheet

# --- LÓGICA DE DISEÑO ---
def generar_diseno(data_input, color_version="AMARILLO"):
    # Detectar si es un grupo (Flyer) o fila única
    is_flyer = isinstance(data_input, pd.DataFrame)
    row = data_input.iloc[0] if is_flyer else data_input
    
    tipo = row['Tipo de diseño']
    formato = row['Formato'].upper()
    path_fonts = f"TIPOGRAFIA/LC/{tipo}"
    path_fondos = f"FONDOS/LC/{tipo}"
    
    # Regla de Colores de Texto
    txt_color = (0,0,0) if color_version == "AMARILLO" else (255,255,255)
    
    # Cargar Fondo
    ext = ".png" if formato == "FLYER" else ".jpg"
    nombre_fondo = f"LC - {tipo} - {formato} FONDO {color_version}{ext}"
    # Ajuste por si el nombre del archivo no lleva espacio (según tus fotos)
    if "FLYER" in formato:
        nombre_fondo = f"LC - {tipo} - FLYER {color_version}{ext}"

    full_path_fondo = os.path.join(path_fondos, nombre_fondo)
    if not os.path.exists(full_path_fondo): return None

    img = Image.open(full_path_fondo).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Selección de Tipografías por Carpeta
    # Usamos Gotham-Bold_0.otf para títulos y Poppins para SKUs
    f_marca = ImageFont.truetype(f"{path_fonts}/Gotham-Bold_0.otf", 40)
    f_prod = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 SemiBold.otf", 30)
    f_precio = ImageFont.truetype(f"{path_fonts}/Gotham-Bold_0.otf", 65)
    f_sku = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 20)

    if formato == "FLYER":
        # Grilla para múltiples productos
        start_x, start_y = 70, 350
        for i, (idx, p_row) in enumerate(data_input.iterrows()):
            if i >= 8: break
            col, r = i % 2, i // 2
            x, y = start_x + (col * 500), start_y + (r * 380)
            
            p_img = Image.open(BytesIO(requests.get(p_row['Foto del producto calado']).content)).convert("RGBA")
            p_img.thumbnail((350, 350))
            img.paste(p_img, (x + 50, y), p_img)
            
            draw.text((x, y + 280), p_row['Marca'], font=f_marca, fill=(0,0,55))
            draw.text((x, y + 320), p_row['Nombre del producto'][:25], font=f_prod, fill=(0,0,0))
            draw.text((x + 300, y + 280), f"S/{p_row['Precio desc']}", font=f_precio, fill=(0,0,55))
    else:
        # PPL, STORY, DISPLAY
        p_img = Image.open(BytesIO(requests.get(row['Foto del producto calado']).content)).convert("RGBA")
        # Coordenadas según tus indicaciones
        if formato == "DISPLAY":
            p_img.thumbnail((450, 450))
            img.paste(p_img, (550, 40), p_img)
            draw.text((60, 180), row['Marca'], font=f_marca, fill=txt_color)
            draw.text((60, 230), row['Nombre del producto'], font=f_prod, fill=txt_color)
            draw.text((60, 310), f"S/ {row['Precio desc']}", font=f_precio, fill=txt_color)
        elif formato == "STORY":
            p_img.thumbnail((800, 800))
            img.paste(p_img, (140, 400), p_img)
            draw.text((100, 1300), row['Marca'], font=f_marca, fill=txt_color)
            draw.text((100, 1350), row['Nombre del producto'], font=f_prod, fill=txt_color)
            draw.text((650, 1330), f"S/ {row['Precio desc']}", font=f_precio, fill=txt_color)

    # Guardado final
    fname = f"{row['SKU'] or row['ID_Flyer']}_{formato}_{color_version}.jpg"
    img.save(f"output/{fname}", quality=95)
    return f"{RAW_URL}{fname}"

# --- EJECUCIÓN ---
data, res_sheet = get_sheets_data()

# Procesar filas
for idx, row in data.iterrows():
    if row['Formato'].upper() == "FLYER": continue # Se procesan aparte
    colores = ["AMARILLO", "AZUL"] if row['Tipo de diseño'] == "DSCTOS POWER" else ["AMARILLO"]
    for c in colores:
        url = generar_diseno(row, c)
        if url: res_sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), row['SKU'], row['Tipo de diseño'], row['Formato'], c, url])

# Procesar grupos de Flyers
flyers = data[data['Formato'].upper() == "FLYER"]
for id_f, group in flyers.groupby('ID_Flyer'):
    if id_f in [0, "0", ""]: continue
    colores = ["AZUL", "AMARILLO"] if group.iloc[0]['Tipo de diseño'] == "DSCTOS POWER" else ["AMARILLO"]
    for c in colores:
        url = generar_diseno(group, c)
        if url: res_sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), id_f, group.iloc[0]['Tipo de diseño'], "FLYER", c, url])