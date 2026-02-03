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
    
    # VOLVEMOS A LECTURA DESDE "Hoja 1"
    data = pd.DataFrame(sheet.worksheet("Hoja 1").get_all_records())
    data.columns = [c.strip() for c in data.columns]
    
    res_sheet = sheet.worksheet("Resultados")
    valores_actuales = res_sheet.get_all_values()
    registros_viejos = set()
    
    if len(valores_actuales) > 1:
        for row in valores_actuales[1:]:
            if len(row) >= 2:
                registros_viejos.add(row[1].strip().upper()) # ID único en Columna B
    
    return data, res_sheet, registros_viejos

def generar_diseno(data_input, color_version="AMARILLO"):
    is_flyer = isinstance(data_input, pd.DataFrame)
    row = data_input.iloc[0] if is_flyer else data_input
    
    tipo = row['Tipo de diseño']
    formato = str(row['Formato']).upper().strip()
    path_fonts = "TIPOGRAFIA/LC"
    path_fondos = f"FONDOS/LC/{tipo}"
    
    txt_color = (0,0,0) if color_version == "AMARILLO" else (255,255,255)
    # Colores Hexadecimales: #FED700 (Amarillo) y #0A063C (Azul)
    border_color = (254, 215, 0) if color_version == "AMARILLO" else (10, 6, 60)
    
    base_name = f"LC - {tipo} - {formato}"
    if formato == "FLYER": base_name = f"LC - {tipo} - FLYER"
    
    full_path_fondo = None
    for ex in [".png", ".jpg", ".PNG", ".JPG"]:
        test_path = os.path.join(path_fondos, f"{base_name} {color_version}{ex}")
        if os.path.exists(test_path):
            full_path_fondo = test_path
            break
    
    if not full_path_fondo: return None

    img = Image.open(full_path_fondo).convert("RGB")
    draw = ImageDraw.Draw(img)

    # --- TIPOGRAFÍA UNIFICADA (HurmeGeometricSans1) ---
    try:
        f_marca = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 44)
        f_prod = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 20)
        f_pre_val = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 72)
        f_pre_sim = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 35)
        f_sku = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 14)
        f_fecha = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 26)
        f_leg_reg = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 11)
    except:
        f_marca = f_prod = f_pre_val = f_pre_sim = f_sku = f_fecha = f_leg_reg = ImageFont.load_default()

    if formato == "FLYER":
        try:
            # 1. Fecha (Alineada a la Izquierda bajo el título)
            fecha_txt = str(row['Fecha_disponibilidad_flyer']).upper()
            w_f = draw.textlength(fecha_txt, font=f_fecha)
            draw.rounded_rectangle([75, 238, 75 + w_f + 40, 290], radius=10, outline=border_color, width=4)
            draw.text((75 + (w_f + 40)//2, 264), fecha_txt, font=f_fecha, fill=border_color, anchor="mm")

            # 2. Cuadrícula Adaptable
            num_p = len(data_input)
            box_h = 330 if num_p > 4 else 460
            start_y = 338 # Margen superior para no chocar
            
            for i, (idx, p_row) in enumerate(data_input.iterrows()):
                if i >= 8: break
                col, f_idx = i % 2, i // 2
                xp, yp = 65 + (col * 495), start_y + (f_idx * (box_h + 12))
                draw.rounded_rectangle([xp, yp, xp+455, yp+box_h], radius=15, fill=(255,255,255), outline=border_color, width=2)
                
                p_res = requests.get(p_row['Foto del producto calado'], timeout=10)
                p_img = quitar_fondo_blanco(Image.open(BytesIO(p_res.content)))
                p_img.thumbnail((box_h-140, box_h-170))
                img.paste(p_img, (int(xp + (455-p_img.width)//2), int(yp + 15)), p_img)

                # Textos Cuadrados (Centrados)
                cl, cr = xp + 115, xp + 345
                draw.text((cl, yp+box_h-105), p_row['Marca'], font=f_marca, fill=(0,0,0), anchor="mm")
                ny = yp + box_h - 60
                for line in textwrap.wrap(p_row['Nombre del producto'], width=18)[:2]:
                    draw.text((cl, ny), line, font=f_prod, fill=(0,0,0), anchor="mm"); ny += 25
                
                p_s = str(p_row['Precio desc'])
                w_s, w_v = draw.textlength("S/", font=f_pre_sim), draw.textlength(p_s, font=f_pre_val)
                px = cr - (w_s + w_v + 5)//2
                draw.text((px, yp+box_h-75), "S/", font=f_pre_sim, fill=(0,0,0), anchor="lm")
                draw.text((px + w_s + 5, yp+box_h-75), p_s, font=f_pre_val, fill=(0,0,0), anchor="lm")
                draw.text((cr, yp+box_h-22), str(p_row['SKU']), font=f_sku, fill=(100,100,100), anchor="mm")

            draw.text((65, 1845), textwrap.fill("CONDICIONES GENERALES: " + str(row['Legales']), width=115), font=f_leg_reg, fill=txt_color)
        except: return None

    else:
        try:
            p_res = requests.get(row['Foto del producto calado'], timeout=10)
            p_img = quitar_fondo_blanco(Image.open(BytesIO(p_res.content)))
            
            if formato == "DISPLAY":
                p_img.thumbnail((440, 440)); img.paste(p_img, (530, 45), p_img)
                cx, ny = 265, 235
                draw.text((cx, 185), row['Marca'], font=f_marca, fill=txt_color, anchor="mt")
                for l in textwrap.wrap(row['Nombre del producto'], width=22):
                    draw.text((cx, ny), l, font=f_prod, fill=txt_color, anchor="mt"); ny += 25
                p_s = str(row['Precio desc'])
                tw = draw.textlength("S/ ", font=f_pre_sim) + draw.textlength(p_s, font=f_pre_val)
                px = cx - tw//2
                draw.text((px, ny+50), "S/ ", font=f_pre_sim, fill=txt_color, anchor="lm")
                draw.text((px + draw.textlength("S/ ", font=f_pre_sim), ny+50), p_s, font=f_pre_val, fill=txt_color, anchor="lm")
                draw.text((cx, ny+115), str(row['SKU']), font=f_sku, fill=txt_color, anchor="mt")
                draw.text((35, 470), textwrap.fill("CONDICIONES GENERALES: " + str(row['Legales']), width=100), font=f_leg_reg, fill=txt_color)

            elif formato == "STORY":
                p_img.thumbnail((750, 750)); img.paste(p_img, (540-p_img.width//2, 650), p_img)
                draw.text((270, 1420), row['Marca'], font=f_marca, fill=txt_color, anchor="mt")
                ny = 1475
                for l in textwrap.wrap(row['Nombre del producto'], width=20):
                    draw.text((270, ny), l, font=f_prod, fill=txt_color, anchor="mt"); ny += 30
                p_s = str(row['Precio desc'])
                tw = draw.textlength("S/ ", font=f_pre_sim) + draw.textlength(p_s, font=f_pre_val)
                px = 810 - tw//2
                draw.text((px, 1475), "S/ ", font=f_pre_sim, fill=txt_color, anchor="mm")
                draw.text((px + 50, 1475), p_s, font=f_pre_val, fill=txt_color, anchor="mm")
                draw.text((810, 1555), str(row['SKU']), font=f_sku, fill=txt_color, anchor="mm")
                draw.text((65, 1850), textwrap.fill("CONDICIONES GENERALES: " + str(row['Legales']), width=110), font=f_leg_reg, fill=txt_color)

            elif formato == "PPL":
                p_img.thumbnail((520, 520)); img.paste(p_img, (500-p_img.width//2, 450-p_img.height//2), p_img)
                draw.text((275, 760), row['Marca'], font=f_marca, fill=txt_color, anchor="mt")
                ny = 810
                for l in textwrap.wrap(row['Nombre del producto'], width=22):
                    draw.text((275, ny), l, font=f_prod, fill=txt_color, anchor="mt"); ny += 28
                p_s = str(row['Precio desc'])
                tw = draw.textlength("S/ ", font=f_pre_sim) + draw.textlength(p_s, font=f_pre_val)
                px = 735 - tw//2
                draw.text((px, 815), "S/ ", font=f_pre_sim, fill=txt_color, anchor="mm")
                draw.text((px + 50, 815), p_s, font=f_pre_val, fill=txt_color, anchor="mm")
                draw.text((735, 890), str(row['SKU']), font=f_sku, fill=txt_color, anchor="mm")
                draw.text((45, 945), textwrap.fill("CONDICIONES GENERALES: " + str(row['Legales']), width=105), font=f_leg_reg, fill=txt_color)
        except: return None

    fname = f"{row['SKU'] or row['ID_Flyer']}_{formato}_{color_version}.jpg"
    img.save(f"output/{fname}", quality=95)
    return f"{RAW_URL}{fname}"

# --- EJECUCIÓN ---
data, res_sheet, registros_viejos = get_sheets_data()
os.makedirs('output', exist_ok=True)
h_lima = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")

# 1. Procesar Individuales
for idx, row in data.iterrows():
    f_val = str(row['Formato']).upper().strip()
    if f_val in ["FLYER", "", "0"]: continue
    for c in (["AMARILLO", "AZUL"] if row['Tipo de diseño'] == "DSCTOS POWER" else ["AMARILLO"]):
        llave = f"{row['SKU']}_{f_val}_{c}".upper()
        if llave not in registros_viejos:
            url = generar_diseno(row, c)
            if url: res_sheet.append_row([h_lima, llave, row['Tipo de diseño'], f_val, c, url])

# 2. Procesar Flyers
fly_g = data[data['Formato'].astype(str).str.upper().str.strip() == "FLYER"]
for id_f, group in fly_g.groupby('ID_Flyer'):
    if str(id_f) in ["0", "0.0", ""]: continue
    for c in (["AZUL", "AMARILLO"] if group.iloc[0]['Tipo de diseño'] == "DSCTOS POWER" else ["AMARILLO"]):
        llave = f"{id_f}_FLYER_{c}".upper()
        if llave not in registros_viejos:
            url = generar_diseno(group, c)
            if url: res_sheet.append_row([h_lima, llave, group.iloc[0]['Tipo de diseño'], "FLYER", c, url])