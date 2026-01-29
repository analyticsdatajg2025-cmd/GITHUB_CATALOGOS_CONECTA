import os
import json
import requests
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
from io import BytesIO
import textwrap # Para el salto de línea automático

# --- CONFIGURACIÓN DE RUTAS Y LINKS ---
USER_GH = "analyticsdatajg2025-cmd"
REPO_GH = "GITHUB_CATALOGOS_CONECTA"
RAW_URL = f"https://raw.githubusercontent.com/{USER_GH}/{REPO_GH}/main/output/"

def quitar_fondo_blanco(img):
    img = img.convert("RGBA")
    datos = img.getdata()
    nueva_data = []
    for item in datos:
        if item[0] > 245 and item[1] > 245 and item[2] > 245:
            nueva_data.append((255, 255, 255, 0))
        else:
            nueva_data.append(item)
    img.putdata(nueva_data)
    return img

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
    
    valores_actuales = res_sheet.get_all_values()
    if not valores_actuales or len(valores_actuales) == 0:
        res_sheet.insert_row(["Fecha", "ID", "Diseño", "Formato", "Color", "Link"], 1)
        valores_actuales = [["Fecha", "ID", "Diseño", "Formato", "Color", "Link"]]
    
    registros_viejos = set()
    if len(valores_actuales) > 1:
        for row in valores_actuales[1:]:
            if len(row) >= 5:
                llave = f"{row[1]}_{row[3]}_{row[4]}".upper()
                registros_viejos.add(llave)
    
    return data, res_sheet, registros_viejos

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
    if not full_path_fondo: return None

    img = Image.open(full_path_fondo).convert("RGB")
    draw = ImageDraw.Draw(img)

    # CARGA DE FUENTES
    try:
        f_marca = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 SemiBold.otf", 24)
        f_prod = ImageFont.truetype(f"{path_fonts}/Gotham-Bold_0.otf", 30)
        f_simbolo = ImageFont.truetype(f"{path_fonts}/Gotham-Bold_0.otf", 45) # S/ más pequeño
        f_precio = ImageFont.truetype(f"{path_fonts}/Gotham-Bold_0.otf", 90) # Número más grande
        f_sku = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 16)
        f_legales_bold = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 11)
        f_legales_reg = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 11) # Usamos la misma pero sin negrita simulada
    except:
        f_marca = f_prod = f_precio = f_simbolo = f_sku = f_legales_bold = f_legales_reg = ImageFont.load_default()

    if formato == "DISPLAY":
        try:
            p_res = requests.get(row['Foto del producto calado'], timeout=10)
            p_img = Image.open(BytesIO(p_res.content)).convert("RGBA")
            p_img = quitar_fondo_blanco(p_img)
            
            # 1. Pegar Imagen (Derecha)
            p_img.thumbnail((450, 450))
            img.paste(p_img, (520, 40), p_img)

            # 2. Textos (Izquierda) - Coordenada X base: 60
            base_x = 60
            y_offset = 180 # Punto de inicio vertical debajo del título del fondo

            # Marca
            draw.text((base_x, y_offset), row['Marca'], font=f_marca, fill=txt_color)
            y_offset += 35

            # Nombre del Producto (con wrap para evitar colisión)
            nombre_wrapped = textwrap.wrap(row['Nombre del producto'], width=25) # Máximo 25 caracteres por línea
            for line in nombre_wrapped:
                draw.text((base_x, y_offset), line, font=f_prod, fill=txt_color)
                y_offset += 35
            
            y_offset += 15 # Espacio antes del precio

            # Precio (S/ pequeño + Número grande)
            simbolo = "S/ "
            precio_str = str(row['Precio desc'])
            # Dibujar S/
            draw.text((base_x, y_offset + 35), simbolo, font=f_simbolo, fill=txt_color)
            # Dibujar número al costado del S/
            draw.text((base_x + 65, y_offset), precio_str, font=f_precio, fill=txt_color)
            y_offset += 100

            # SKU
            draw.text((base_x, y_offset), f"SKU: {row['SKU']}", font=f_sku, fill=txt_color)

            # 3. Legales (Inferior Izquierda)
            legales_y = 485
            text_bold = "CONDICIONES GENERALES: "
            text_reg = str(row['Legales'])
            
            # Dibujar negrita
            draw.text((20, legales_y), text_bold, font=f_legales_bold, fill=txt_color)
            # Dibujar el resto del texto después de la negrita
            offset_legal = draw.textlength(text_bold, font=f_legales_bold)
            draw.text((20 + offset_legal, legales_y), text_reg, font=f_legales_reg, fill=txt_color)

        except Exception as e:
            print(f"Error en DISPLAY: {e}")
            return None

    # Lógica para otros formatos (PPL, STORY, FLYER) se mantiene igual por ahora
    elif formato == "STORY":
        # ... (Mantener tu código anterior para Story)
        p_res = requests.get(row['Foto del producto calado'], timeout=10)
        p_img = Image.open(BytesIO(p_res.content)).convert("RGBA")
        p_img = quitar_fondo_blanco(p_img)
        p_img.thumbnail((800, 800))
        img.paste(p_img, (140, 420), p_img)
        draw.text((100, 1280), row['Marca'], font=f_marca, fill=txt_color)
        draw.text((100, 1340), row['Nombre del producto'], font=f_prod, fill=txt_color)
        draw.text((100, 1450), f"S/ {row['Precio desc']}", font=f_precio, fill=txt_color)
        draw.text((50, 1880), row['Legales'], font=f_legales_reg, fill=txt_color)
    elif formato == "PPL":
        # ... (Mantener tu código anterior para PPL)
        p_res = requests.get(row['Foto del producto calado'], timeout=10)
        p_img = Image.open(BytesIO(p_res.content)).convert("RGBA")
        p_img = quitar_fondo_blanco(p_img)
        p_img.thumbnail((720, 720))
        img.paste(p_img, (140, 60), p_img)
        draw.text((70, 760), row['Marca'], font=f_marca, fill=txt_color)
        draw.text((70, 810), row['Nombre del producto'], font=f_prod, fill=txt_color)
        draw.text((630, 780), f"S/ {row['Precio desc']}", font=f_precio, fill=txt_color)
        draw.text((40, 960), row['Legales'], font=f_legales_reg, fill=txt_color)
    elif formato == "FLYER":
        # ... (Mantener tu código anterior para Flyer)
        start_x, start_y = 65, 360
        for i, (idx, p_row) in enumerate(data_input.iterrows()):
            if i >= 8: break
            col, r = i % 2, i // 2
            x, y = start_x + (col * 495), start_y + (r * 375)
            try:
                p_res = requests.get(p_row['Foto del producto calado'], timeout=10)
                p_img = Image.open(BytesIO(p_res.content)).convert("RGBA")
                p_img = quitar_fondo_blanco(p_img)
                p_img.thumbnail((320, 320))
                img.paste(p_img, (x + 80, y), p_img)
                draw.text((x + 10, y + 270), p_row['Marca'], font=f_marca, fill=(0,0,50))
                draw.text((x + 10, y + 310), p_row['Nombre del producto'][:25], font=f_prod, fill=(0,0,0))
                draw.text((x + 300, y + 270), f"S/{p_row['Precio desc']}", font=f_precio, fill=(0,0,50))
            except: continue
        draw.text((50, 1850), row['Legales'], font=f_legales_reg, fill=(255,255,255))

    fname = f"{row['SKU'] or row['ID_Flyer']}_{formato}_{color_version}.jpg"
    img.save(f"output/{fname}", quality=95)
    return f"{RAW_URL}{fname}"

# --- EJECUCIÓN PRINCIPAL ---
data, res_sheet, registros_existentes = get_sheets_data()
os.makedirs('output', exist_ok=True)
hora_lima = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")

# 1. Individuales
for idx, row in data.iterrows():
    if str(row['Formato']).upper() == "FLYER": continue
    colores = ["AMARILLO", "AZUL"] if row['Tipo de diseño'] == "DSCTOS POWER" else ["AMARILLO"]
    for c in colores:
        llave_actual = f"{row['SKU']}_{row['Formato']}_{c}".upper()
        if llave_actual in registros_existentes: continue
        url = generar_diseno(row, c)
        if url: res_sheet.append_row([hora_lima, row['SKU'], row['Tipo de diseño'], row['Formato'], c, url])

# 2. Flyers
flyers_group = data[data['Formato'].astype(str).str.upper() == "FLYER"]
for id_f, group in flyers_group.groupby('ID_Flyer'):
    if str(id_f) in ["0", "0.0", ""]: continue
    colores = ["AZUL", "AMARILLO"] if group.iloc[0]['Tipo de diseño'] == "DSCTOS POWER" else ["AMARILLO"]
    for c in colores:
        llave_flyer = f"{id_f}_FLYER_{c}".upper()
        if llave_flyer in registros_existentes: continue
        url = generar_diseno(group, c)
        if url: res_sheet.append_row([hora_lima, str(id_f), group.iloc[0]['Tipo de diseño'], "FLYER", c, url])