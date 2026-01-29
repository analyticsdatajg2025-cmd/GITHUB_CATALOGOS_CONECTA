import os
import json
import requests
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta # Para la hora de Perú
from io import BytesIO

# --- CONFIGURACIÓN DE RUTAS Y LINKS ---
USER_GH = "analyticsdatajg2025-cmd"
REPO_GH = "GITHUB_CATALOGOS_CONECTA"
RAW_URL = f"https://raw.githubusercontent.com/{USER_GH}/{REPO_GH}/main/output/"

# --- FUNCIÓN PARA QUITAR FONDO BLANCO ---
def quitar_fondo_blanco(img):
    img = img.convert("RGBA")
    datos = img.getdata()
    nueva_data = []
    for item in datos:
        # Si el píxel es muy cercano al blanco (R, G, B > 245), lo volvemos transparente
        if item[0] > 245 and item[1] > 245 and item[2] > 245:
            nueva_data.append((255, 255, 255, 0))
        else:
            nueva_data.append(item)
    img.putdata(nueva_data)
    return img

# --- CONEXIÓN A GOOGLE SHEETS ---
def get_sheets_data():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_info = json.loads(os.environ.get('GOOGLE_CREDENTIALS'))
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key("1PmvCyC3d0VvvZSdvWM73NYusrYevVYtRzVs2gbxjw1M")
    
    data = pd.DataFrame(sheet.worksheet("Hoja 1").get_all_records())
    
    try:
        res_sheet = sheet.worksheet("Resultados")
    except:
        res_sheet = sheet.add_worksheet(title="Resultados", rows="1000", cols="10")
    
    # Verificación robusta de encabezados
    valores_actuales = res_sheet.get_all_values()
    if not valores_actuales or len(valores_actuales) == 0:
        res_sheet.insert_row(["Fecha", "ID", "Diseño", "Formato", "Color", "Link"], 1)
    
    return data, res_sheet

# --- LÓGICA DE DISEÑO ---
def generar_diseno(data_input, color_version="AMARILLO"):
    is_flyer = isinstance(data_input, pd.DataFrame)
    row = data_input.iloc[0] if is_flyer else data_input
    
    tipo = row['Tipo de diseño']
    formato = str(row['Formato']).upper()
    path_fonts = f"TIPOGRAFIA/LC/{tipo}"
    path_fondos = f"FONDOS/LC/{tipo}"
    
    txt_color = (0,0,0) if color_version == "AMARILLO" else (255,255,255)
    
    ext = ".png" if formato == "FLYER" else ".jpg"
    posibles_nombres = [
        f"LC - {tipo} - {formato} FONDO {color_version}{ext}",
        f"LC -  {tipo} - {formato} FONDO {color_version}{ext}",
        f"LC - {tipo} - {formato} {color_version}{ext}",
        f"LC -  {tipo} - {formato} {color_version}{ext}"
    ]
    
    if "FLYER" in formato:
        posibles_nombres.extend([f"LC - {tipo} - FLYER {color_version}{ext}", f"LC -  {tipo} - FLYER {color_version}{ext}"])

    full_path_fondo = next((os.path.join(path_fondos, n) for n in posibles_nombres if os.path.exists(os.path.join(path_fondos, n))), None)

    if not full_path_fondo:
        return None

    img = Image.open(full_path_fondo).convert("RGB")
    draw = ImageDraw.Draw(img)

    try:
        f_marca = ImageFont.truetype(f"{path_fonts}/Gotham-Bold_0.otf", 40)
        f_prod = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 SemiBold.otf", 30)
        f_precio = ImageFont.truetype(f"{path_fonts}/Gotham-Bold_0.otf", 70)
        f_legales = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 15)
    except:
        f_marca = f_prod = f_precio = f_legales = ImageFont.load_default()

    if formato == "FLYER":
        start_x, start_y = 65, 360
        for i, (idx, p_row) in enumerate(data_input.iterrows()):
            if i >= 8: break
            col, r = i % 2, i // 2
            x, y = start_x + (col * 495), start_y + (r * 375)
            
            try:
                p_res = requests.get(p_row['Foto del producto calado'], timeout=10)
                p_img = Image.open(BytesIO(p_res.content)).convert("RGBA")
                # QUITAR FONDO BLANCO
                p_img = quitar_fondo_blanco(p_img)
                p_img.thumbnail((320, 320))
                img.paste(p_img, (x + 80, y), p_img)
                
                draw.text((x + 10, y + 270), p_row['Marca'], font=f_marca, fill=(0,0,50))
                draw.text((x + 10, y + 310), p_row['Nombre del producto'][:25], font=f_prod, fill=(0,0,0))
                draw.text((x + 300, y + 270), f"S/{p_row['Precio desc']}", font=f_precio, fill=(0,0,50))
            except: continue
        draw.text((50, 1850), row['Legales'], font=f_legales, fill=(255,255,255))

    else:
        try:
            p_res = requests.get(row['Foto del producto calado'], timeout=10)
            p_img = Image.open(BytesIO(p_res.content)).convert("RGBA")
            # QUITAR FONDO BLANCO
            p_img = quitar_fondo_blanco(p_img)
            
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

    fname = f"{row['SKU'] or row['ID_Flyer']}_{formato}_{color_version}.jpg"
    img.save(f"output/{fname}", quality=95)
    return f"{RAW_URL}{fname}"

# --- EJECUCIÓN ---
data, res_sheet = get_sheets_data()
os.makedirs('output', exist_ok=True)

# HORA LIMA (UTC-5)
hora_lima = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")

for idx, row in data.iterrows():
    if str(row['Formato']).upper() == "FLYER": continue
    colores = ["AMARILLO", "AZUL"] if row['Tipo de diseño'] == "DSCTOS POWER" else ["AMARILLO"]
    for c in colores:
        url = generar_diseno(row, c)
        if url:
            res_sheet.append_row([hora_lima, row['SKU'], row['Tipo de diseño'], row['Formato'], c, url])

flyers_group = data[data['Formato'].astype(str).str.upper() == "FLYER"]
for id_f, group in flyers_group.groupby('ID_Flyer'):
    if str(id_f) in ["0", "0.0", ""]: continue
    colores = ["AZUL", "AMARILLO"] if group.iloc[0]['Tipo de diseño'] == "DSCTOS POWER" else ["AMARILLO"]
    for c in colores:
        url = generar_diseno(group, c)
        if url:
            res_sheet.append_row([hora_lima, str(id_f), group.iloc[0]['Tipo de diseño'], "FLYER", c, url])