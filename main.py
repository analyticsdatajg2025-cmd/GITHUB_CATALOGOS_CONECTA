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
    creds_info = json.loads(os.environ.get('GOOGLE_CREDENTIALS'))
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key("1PmvCyC3d0VvvZSdvWM73NYusrYevVYtRzVs2gbxjw1M")
    
    data = pd.DataFrame(sheet.worksheet("Hoja 1").get_all_records())
    
    # Manejo de Hoja Resultados
    try:
        res_sheet = sheet.worksheet("Resultados")
    except:
        res_sheet = sheet.add_worksheet(title="Resultados", rows="1000", cols="10")
    
    if not res_sheet.get_all_values():
        res_sheet.append_row(["Fecha", "ID", "Diseño", "Formato", "Color", "Link"])
    
    return data, res_sheet

# --- LÓGICA DE DISEÑO ---
def generar_diseno(data_input, color_version="AMARILLO"):
    is_flyer = isinstance(data_input, pd.DataFrame)
    row = data_input.iloc[0] if is_flyer else data_input
    
    tipo = row['Tipo de diseño']
    formato = str(row['Formato']).upper()
    path_fonts = f"TIPOGRAFIA/LC/{tipo}"
    path_fondos = f"FONDOS/LC/{tipo}"
    
    # Regla: Amarillo -> Texto Negro | Azul -> Texto Blanco
    txt_color = (0,0,0) if color_version == "AMARILLO" else (255,255,255)
    
    # LÓGICA DE BÚSQUEDA DE ARCHIVO (Flexible con espacios dobles)
    ext = ".png" if formato == "FLYER" else ".jpg"
    posibles_nombres = [
        f"LC - {tipo} - {formato} FONDO {color_version}{ext}",
        f"LC -  {tipo} - {formato} FONDO {color_version}{ext}", # Caso doble espacio
        f"LC - {tipo} - {formato} {color_version}{ext}",
        f"LC -  {tipo} - {formato} {color_version}{ext}"
    ]
    
    if "FLYER" in formato:
        posibles_nombres.extend([
            f"LC - {tipo} - FLYER {color_version}{ext}",
            f"LC -  {tipo} - FLYER {color_version}{ext}"
        ])

    full_path_fondo = next((os.path.join(path_fondos, n) for n in posibles_nombres if os.path.exists(os.path.join(path_fondos, n))), None)

    if not full_path_fondo:
        print(f"Archivo no encontrado para: {tipo} {formato} {color_version}")
        return None

    img = Image.open(full_path_fondo).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Cargar Fuentes según tu estructura
    try:
        f_marca = ImageFont.truetype(f"{path_fonts}/Gotham-Bold_0.otf", 40)
        f_prod = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 SemiBold.otf", 30)
        f_precio = ImageFont.truetype(f"{path_fonts}/Gotham-Bold_0.otf", 70)
        f_legales = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 15)
    except:
        f_marca = f_prod = f_precio = f_legales = ImageFont.load_default()

    if formato == "FLYER":
        # Grilla para múltiples productos (hasta 8)
        start_x, start_y = 65, 360
        for i, (idx, p_row) in enumerate(data_input.iterrows()):
            if i >= 8: break
            col, r = i % 2, i // 2
            x, y = start_x + (col * 495), start_y + (r * 375)
            
            try:
                p_res = requests.get(p_row['Foto del producto calado'], timeout=10)
                p_img = Image.open(BytesIO(p_res.content)).convert("RGBA")
                p_img.thumbnail((320, 320))
                img.paste(p_img, (x + 80, y), p_img)
                
                # Textos del Flyer
                draw.text((x + 10, y + 270), p_row['Marca'], font=f_marca, fill=(0,0,50))
                draw.text((x + 10, y + 310), p_row['Nombre del producto'][:25], font=f_prod, fill=(0,0,0))
                draw.text((x + 300, y + 270), f"S/{p_row['Precio desc']}", font=f_precio, fill=(0,0,50))
            except: continue
        
        # Legales únicos al final del Flyer
        draw.text((50, 1850), row['Legales'], font=f_legales, fill=(255,255,255))

    else:
        # DISPLAY, STORY, PPL
        try:
            p_res = requests.get(row['Foto del producto calado'], timeout=10)
            p_img = Image.open(BytesIO(p_res.content)).convert("RGBA")
            
            if formato == "DISPLAY":
                p_img.thumbnail((450, 450))
                img.paste(p_img, (530, 45), p_img)
                draw.text((60, 180), row['Marca'], font=f_marca, fill=txt_color)
                draw.text((60, 230), row['Nombre del producto'], font=f_prod, fill=txt_color)
                draw.text((60, 310), f"S/ {row['Precio desc']}", font=f_precio, fill=txt_color)
                draw.text((40, 490), row['Legales'], font=f_legales, fill=txt_color)
            elif formato == "STORY":
                p_img.thumbnail((800, 800))
                img.paste(p_img, (140, 420), p_img)
                draw.text((100, 1280), row['Marca'], font=f_marca, fill=txt_color)
                draw.text((100, 1340), row['Nombre del producto'], font=f_prod, fill=txt_color)
                draw.text((100, 1450), f"S/ {row['Precio desc']}", font=f_precio, fill=txt_color)
                draw.text((50, 1880), row['Legales'], font=f_legales, fill=txt_color)
            elif formato == "PPL":
                p_img.thumbnail((720, 720))
                img.paste(p_img, (140, 60), p_img)
                draw.text((70, 760), row['Marca'], font=f_marca, fill=txt_color)
                draw.text((70, 810), row['Nombre del producto'], font=f_prod, fill=txt_color)
                draw.text((630, 780), f"S/ {row['Precio desc']}", font=f_precio, fill=txt_color)
                draw.text((40, 960), row['Legales'], font=f_legales, fill=txt_color)
        except: return None

    # Guardado
    fname = f"{row['SKU'] or row['ID_Flyer']}_{formato}_{color_version}.jpg"
    img.save(f"output/{fname}", quality=95)
    return f"{RAW_URL}{fname}"

# --- EJECUCIÓN ---
data, res_sheet = get_sheets_data()
os.makedirs('output', exist_ok=True)

# 1. Procesar Individuales
for idx, row in data.iterrows():
    if str(row['Formato']).upper() == "FLYER": continue
    colores = ["AMARILLO", "AZUL"] if row['Tipo de diseño'] == "DSCTOS POWER" else ["AMARILLO"]
    for c in colores:
        url = generar_diseno(row, c)
        if url:
            res_sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), row['SKU'], row['Tipo de diseño'], row['Formato'], c, url])

# 2. Procesar Flyers (Grouped)
# Corrección del error 'AttributeError' usando .str.upper()
flyers_group = data[data['Formato'].astype(str).str.upper() == "FLYER"]
for id_f, group in flyers_group.groupby('ID_Flyer'):
    if str(id_f) in ["0", "0.0", ""]: continue
    colores = ["AZUL", "AMARILLO"] if group.iloc[0]['Tipo de diseño'] == "DSCTOS POWER" else ["AMARILLO"]
    for c in colores:
        url = generar_diseno(group, c)
        if url:
            res_sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), str(id_f), group.iloc[0]['Tipo de diseño'], "FLYER", c, url])