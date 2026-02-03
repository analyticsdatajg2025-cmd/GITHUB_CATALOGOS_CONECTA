import os
import json
import requests
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
from io import BytesIO
import textwrap 

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
    registros_viejos = set()
    if len(valores_actuales) > 1:
        for row in valores_actuales[1:]:
            if len(row) >= 5:
                llave = f"{row[1]}_{row[3]}_{row[4]}".upper()
                registros_viejos.add(llave)
    
    return data, res_sheet, registros_viejos

def generar_diseno(data_input, color_version="AMARILLO"):
    is_flyer = isinstance(data_input, pd.DataFrame)
    row = data_input.iloc[0] if is_flyer else data_input
    
    tipo = row['Tipo de diseño']
    formato = str(row['Formato']).upper()
    path_fonts = "TIPOGRAFIA/LC" # RUTA UNIFICADA
    path_fondos = f"FONDOS/LC/{tipo}"
    
    txt_color = (0,0,0) if color_version == "AMARILLO" else (255,255,255)
    accent_color = (255, 230, 0) if color_version == "AZUL" else (0, 0, 0)
    
    ext = ".png" if formato == "FLYER" else ".jpg"
    posibles_nombres = [
        f"LC - {tipo} - {formato} FONDO {color_version}{ext}",
        f"LC - {tipo} - {formato} {color_version}{ext}"
    ]
    if "FLYER" in formato:
        posibles_nombres.extend([f"LC - {tipo} - FLYER {color_version}{ext}"])

    full_path_fondo = next((os.path.join(path_fondos, n) for n in posibles_nombres if os.path.exists(os.path.join(path_fondos, n))), None)
    if not full_path_fondo: return None

    img = Image.open(full_path_fondo).convert("RGB")
    draw = ImageDraw.Draw(img)

    # --- FUENTES ACTUALIZADAS ---
    try:
        f_marca = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 35) # Más notoriedad
        f_prod = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 24) # Tamaño reducido
        f_precio = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 85)
        f_sku = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 14)
        f_fecha = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 26)
        f_leg_bold = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 13)
        f_leg_reg = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 10)
    except:
        f_marca = f_prod = f_precio = f_sku = f_fecha = f_leg_bold = f_leg_reg = ImageFont.load_default()

    if formato == "FLYER":
        try:
            # 1. Fecha Dinámica (Debajo del Título de Fondo)
            fecha_txt = str(row['Fecha_disponibilidad_flyer']).upper()
            w_f = draw.textlength(fecha_txt, font=f_fecha)
            # Dibujar etiqueta de fecha centrada arriba
            draw.rounded_rectangle([540-(w_f/2)-20, 230, 540+(w_f/2)+20, 280], radius=10, outline=accent_color, width=3)
            draw.text((540, 255), fecha_txt, font=f_fecha, fill=accent_color, anchor="mm")

            # 2. Cuadrícula adaptable (Máx 8)
            num_prod = len(data_input)
            box_h = 320 if num_prod > 4 else 450 # Ajuste de tamaño según cantidad
            start_y = 320
            margin_y = 15
            
            for i, (idx, p_row) in enumerate(data_input.iterrows()):
                if i >= 8: break
                col, fila = i % 2, i // 2
                x_p = 60 + (col * 500)
                y_p = start_y + (fila * (box_h + margin_y))

                # Cuadro de producto
                draw.rounded_rectangle([x_p, y_p, x_p+460, y_p+box_h], radius=15, fill=(255,255,255), outline=(220,220,220), width=1)
                
                # Imagen del producto
                p_res = requests.get(p_row['Foto del producto calado'], timeout=10)
                p_img = Image.open(BytesIO(p_res.content)).convert("RGBA")
                p_img = quitar_fondo_blanco(p_img)
                p_img.thumbnail((box_h-100, box_h-150))
                img.paste(p_img, (int(x_p + (460-p_img.width)//2), int(y_p + 15)), p_img)

                # Info de producto
                center_l = x_p + 115
                center_r = x_p + 345
                draw.text((center_l, y_p+box_h-80), p_row['Marca'], font=f_marca, fill=(0,0,0), anchor="mm")
                
                wrap_n = textwrap.wrap(p_row['Nombre del producto'], width=18)
                ny = y_p + box_h - 45
                for line in wrap_n[:2]:
                    draw.text((center_l, ny), line, font=f_prod, fill=(0,0,0), anchor="mm")
                    ny += 25
                
                draw.text((center_r, y_p+box_h-60), f"S/{p_row['Precio desc']}", font=f_precio, fill=(0,0,0), anchor="mm")
                draw.text((center_r, y_p+box_h-20), str(p_row['SKU']), font=f_sku, fill=(80,80,80), anchor="mm")

            # 3. Legales con Wrap
            legales_y = 1840
            text_legal = "CONDICIONES GENERALES: " + str(row['Legales'])
            wrapped_leg = textwrap.fill(text_legal, width=105)
            draw.text((60, legales_y), wrapped_leg, font=f_leg_reg, fill=txt_color)

        except Exception as e:
            print(f"Error en FLYER: {e}")
            return None

    else:
        # DISPLAY, STORY, PPL
        try:
            p_res = requests.get(row['Foto del producto calado'], timeout=10)
            p_img = Image.open(BytesIO(p_res.content)).convert("RGBA")
            p_img = quitar_fondo_blanco(p_img)
            
            if formato == "DISPLAY":
                p_img.thumbnail((440, 440))
                img.paste(p_img, (530, 45), p_img)
                # Textos Izquierda centrados
                cx = 265
                draw.text((cx, 185), row['Marca'], font=f_marca, fill=txt_color, anchor="mt")
                nombre_w = textwrap.wrap(row['Nombre del producto'], width=20)
                ny = 230
                for l in nombre_w:
                    draw.text((cx, ny), l, font=f_prod, fill=txt_color, anchor="mt")
                    ny += 28
                draw.text((cx, ny+15), f"S/ {row['Precio desc']}", font=f_precio, fill=txt_color, anchor="mt")
                draw.text((cx, ny+105), str(row['SKU']), font=f_sku, fill=txt_color, anchor="mt")
                # Legales
                leg_w = textwrap.fill("CONDICIONES GENERALES: " + str(row['Legales']), width=90)
                draw.text((25, 460), leg_w, font=f_leg_reg, fill=txt_color)

            elif formato == "STORY":
                p_img.thumbnail((750, 750))
                img.paste(p_img, (540-p_img.width//2, 650), p_img)
                draw.text((270, 1420), row['Marca'], font=f_marca, fill=txt_color, anchor="mt")
                nombre_w = textwrap.wrap(row['Nombre del producto'], width=18)
                ny = 1465
                for l in nombre_w:
                    draw.text((270, ny), l, font=f_prod, fill=txt_color, anchor="mt")
                    ny += 35
                draw.text((810, 1455), f"S/ {row['Precio desc']}", font=f_precio, fill=txt_color, anchor="mm")
                draw.text((810, 1545), str(row['SKU']), font=f_sku, fill=txt_color, anchor="mm")
                leg_w = textwrap.fill("CONDICIONES GENERALES: " + str(row['Legales']), width=100)
                draw.text((60, 1840), leg_w, font=f_leg_reg, fill=txt_color)

            elif formato == "PPL":
                p_img.thumbnail((520, 520))
                img.paste(p_img, (500-p_img.width//2, 450-p_img.height//2), p_img)
                draw.text((270, 760), row['Marca'], font=f_marca, fill=txt_color, anchor="mt")
                nombre_w = textwrap.wrap(row['Nombre del producto'], width=20)
                ny = 800
                for l in nombre_w:
                    draw.text((270, ny), l, font=f_prod, fill=txt_color, anchor="mt")
                    ny += 32
                draw.text((730, 795), f"S/ {row['Precio desc']}", font=f_precio, fill=txt_color, anchor="mm")
                draw.text((730, 870), str(row['SKU']), font=f_sku, fill=txt_color, anchor="mm")
                leg_w = textwrap.fill("CONDICIONES GENERALES: " + str(row['Legales']), width=95)
                draw.text((40, 935), leg_w, font=f_leg_reg, fill=txt_color)

        except: return None

    fname = f"{row['SKU'] or row['ID_Flyer']}_{formato}_{color_version}.jpg"
    img.save(f"output/{fname}", quality=95)
    return f"{RAW_URL}{fname}"

# --- EJECUCIÓN ---
data, res_sheet, registros_existentes = get_sheets_data()
os.makedirs('output', exist_ok=True)
h_lima = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")

for idx, row in data.iterrows():
    if str(row['Formato']).upper() == "FLYER": continue
    colores = ["AMARILLO", "AZUL"] if row['Tipo de diseño'] == "DSCTOS POWER" else ["AMARILLO"]
    for c in colores:
        llave = f"{row['SKU']}_{row['Formato']}_{c}".upper()
        if llave not in registros_existentes:
            url = generar_diseno(row, c)
            if url: res_sheet.append_row([h_lima, row['SKU'], row['Tipo de diseño'], row['Formato'], c, url])

fly_g = data[data['Formato'].astype(str).str.upper() == "FLYER"]
for id_f, group in fly_g.groupby('ID_Flyer'):
    if str(id_f) in ["0", "0.0", ""]: continue
    colores = ["AZUL", "AMARILLO"] if group.iloc[0]['Tipo de diseño'] == "DSCTOS POWER" else ["AMARILLO"]
    for c in colores:
        llave = f"{id_f}_FLYER_{c}".upper()
        if llave not in registros_existentes:
            url = generar_diseno(group, c)
            if url: res_sheet.append_row([h_lima, str(id_f), group.iloc[0]['Tipo de diseño'], "FLYER", c, url])
