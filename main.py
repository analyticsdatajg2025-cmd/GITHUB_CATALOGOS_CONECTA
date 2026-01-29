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
    
    # Regla base de colores de texto
    txt_color = (0,0,0) if color_version == "AMARILLO" else (255,255,255)
    accent_color = (255, 230, 0) if color_version == "AZUL" else (0, 0, 0)
    
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

    # FUENTES
    try:
        f_marca = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 SemiBold.otf", 22)
        f_prod = ImageFont.truetype(f"{path_fonts}/Gotham-Bold_0.otf", 24)
        f_simbolo = ImageFont.truetype(f"{path_fonts}/Gotham-Bold_0.otf", 35)
        f_precio = ImageFont.truetype(f"{path_fonts}/Gotham-Bold_0.otf", 75)
        f_sku = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 14)
        f_fecha = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 28)
        f_leg_bold = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 14)
        f_leg_reg = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 10)
    except:
        f_marca = f_prod = f_precio = f_simbolo = f_sku = f_fecha = f_leg_bold = f_leg_reg = ImageFont.load_default()

    if formato == "FLYER":
        try:
            # 1. Etiqueta de Fecha (Top)
            fecha_txt = str(row['Fecha_disponibilidad_flyer']).upper()
            w_f = draw.textlength(fecha_txt, font=f_fecha)
            # Dibujar contorno de fecha (rectángulo redondeado)
            draw.rounded_rectangle([540 - (w_f/2) - 20, 115, 540 + (w_f/2) + 20, 165], radius=15, outline=accent_color, width=3)
            draw.text((540, 140), fecha_txt, font=f_fecha, fill=accent_color, anchor="mm")

            # 2. Cuadrícula de Productos (Máx 8, 2 por fila)
            start_y = 350
            box_w, box_h = 460, 360
            margin_x, margin_y = 60, 25

            for i, (idx, p_row) in enumerate(data_input.iterrows()):
                if i >= 8: break
                col, fila_idx = i % 2, i // 2
                x_pos = margin_x + (col * (box_w + 40))
                y_pos = start_y + (fila_idx * (box_h + margin_y))

                # Dibujar cuadro del producto (blanco con borde fino)
                draw.rounded_rectangle([x_pos, y_pos, x_pos + box_w, y_pos + box_h], radius=20, fill=(255,255,255), outline=(200,200,200), width=2)

                # Imagen del producto
                p_res = requests.get(p_row['Foto del producto calado'], timeout=10)
                p_img = Image.open(BytesIO(p_res.content)).convert("RGBA")
                p_img = quitar_fondo_blanco(p_img)
                p_img.thumbnail((280, 200))
                img.paste(p_img, (int(x_pos + (box_w - p_img.width)//2), int(y_pos + 20)), p_img)

                # Coordenadas internas para textos
                y_text = y_pos + 235
                l_center = x_pos + (box_w // 4)
                r_center = x_pos + (3 * box_w // 4)

                # Izquierda: Marca y Nombre
                draw.text((l_center, y_text), p_row['Marca'], font=f_marca, fill=(0,0,0), anchor="mm")
                p_name_y = y_text + 35
                wrap_n = textwrap.wrap(p_row['Nombre del producto'], width=15)
                for line in wrap_n[:2]:
                    draw.text((l_center, p_name_y), line, font=f_prod, fill=(0,0,0), anchor="mm")
                    p_name_y += 28

                # Derecha: Precio y SKU
                p_str = str(p_row['Precio desc'])
                w_s = draw.textlength("S/", font=f_simbolo)
                w_m = draw.textlength(p_str, font=f_precio)
                p_start_x = r_center - (w_s + w_m)//2
                draw.text((p_start_x, y_text + 25), "S/", font=f_simbolo, fill=(0,0,0), anchor="lm")
                draw.text((p_start_x + w_s, y_text + 25), p_str, font=f_precio, fill=(0,0,0), anchor="lm")
                draw.text((r_center, y_text + 85), str(p_row['SKU']), font=f_sku, fill=(100,100,100), anchor="mm")

            # 3. Legales (Bottom)
            legales_y = 1860
            text_bold = "CONDICIONES GENERALES: "
            draw.text((60, legales_y), text_bold, font=f_leg_bold, fill=txt_color)
            off_l = draw.textlength(text_bold, font=f_leg_bold)
            draw.text((60 + off_l, legales_y + 3), str(row['Legales']), font=f_leg_reg, fill=txt_color)

        except Exception as e:
            print(f"Error en FLYER: {e}")
            return None

    # Lógica para DISPLAY, PPL y STORY (Sin cambios)
    elif formato == "DISPLAY":
        try:
            p_res = requests.get(row['Foto del producto calado'], timeout=10)
            p_img = Image.open(BytesIO(p_res.content)).convert("RGBA")
            p_img = quitar_fondo_blanco(p_img)
            p_img.thumbnail((440, 440))
            img.paste(p_img, (530, 45), p_img)
            center_x = 250
            y_offset = 185 
            draw.text((center_x, y_offset), row['Marca'], font=f_marca, fill=txt_color, anchor="mt")
            y_offset += 38
            nombre_wrapped = textwrap.wrap(row['Nombre del producto'], width=22)
            for line in nombre_wrapped:
                draw.text((center_x, y_offset), line, font=f_prod, fill=txt_color, anchor="mt")
                y_offset += 32
            y_offset += 15 
            precio_str = str(row['Precio desc'])
            w_simbolo = draw.textlength("S/ ", font=f_simbolo)
            w_monto = draw.textlength(precio_str, font=f_precio)
            total_p_w = w_simbolo + w_monto
            price_start_x = center_x - (total_p_w / 2)
            draw.text((price_start_x, y_offset + 35), "S/ ", font=f_simbolo, fill=txt_color)
            draw.text((price_start_x + w_simbolo, y_offset), precio_str, font=f_precio, fill=txt_color)
            y_offset += 105
            draw.text((center_x, y_offset), str(row['SKU']), font=f_sku, fill=txt_color, anchor="mt")
            legales_y = 455 
            text_bold = "CONDICIONES GENERALES: "
            text_reg = str(row['Legales'])
            draw.text((25, legales_y), text_bold, font=f_leg_bold, fill=txt_color)
            offset_legal = draw.textlength(text_bold, font=f_leg_bold)
            draw.text((25 + offset_legal, legales_y + 3), text_reg, font=f_leg_reg, fill=txt_color)
        except: return None

    elif formato == "PPL":
        try:
            p_res = requests.get(row['Foto del producto calado'], timeout=10)
            p_img = Image.open(BytesIO(p_res.content)).convert("RGBA")
            p_img = quitar_fondo_blanco(p_img)
            p_img.thumbnail((520, 520))
            img.paste(p_img, (500 - p_img.width // 2, 450 - p_img.height // 2), p_img)
            l_center_x, r_center_x, y_start = 270, 730, 760 
            draw.text((l_center_x, y_start), row['Marca'], font=f_marca, fill=txt_color, anchor="mt")
            p_name_y = y_start + 40
            wrap_p = textwrap.wrap(row['Nombre del producto'], width=20)
            for line in wrap_p:
                draw.text((l_center_x, p_name_y), line, font=f_prod, fill=txt_color, anchor="mt")
                p_name_y += 32
            precio_str = str(row['Precio desc'])
            total_p_w = draw.textlength("S/ ", font=f_simbolo) + draw.textlength(precio_str, font=f_precio)
            p_x = r_center_x - (total_p_w / 2)
            draw.text((p_x, y_start + 35), "S/ ", font=f_simbolo, fill=txt_color)
            draw.text((p_x + draw.textlength("S/ ", font=f_simbolo), y_start), precio_str, font=f_precio, fill=txt_color)
            draw.text((r_center_x, y_start + 110), str(row['SKU']), font=f_sku, fill=txt_color, anchor="mt")
            draw.text((40, 945), "CONDICIONES GENERALES: ", font=f_leg_bold, fill=txt_color)
            draw.text((40 + draw.textlength("CONDICIONES GENERALES: ", font=f_leg_bold), 948), str(row['Legales']), font=f_leg_reg, fill=txt_color)
        except: return None

    elif formato == "STORY":
        try:
            p_res = requests.get(row['Foto del producto calado'], timeout=10)
            p_img = Image.open(BytesIO(p_res.content)).convert("RGBA")
            p_img = quitar_fondo_blanco(p_img)
            p_img.thumbnail((750, 750))
            img.paste(p_img, (540 - p_img.width // 2, 650), p_img)
            l_c, r_c, y_s = 270, 810, 1420 
            draw.text((l_c, y_s), row['Marca'], font=f_marca, fill=txt_color, anchor="mt")
            p_n_y = y_s + 45
            wrap_s = textwrap.wrap(row['Nombre del producto'], width=18)
            for line in wrap_s:
                draw.text((l_c, p_n_y), line, font=f_prod, fill=txt_color, anchor="mt")
                p_n_y += 35
            p_str = str(row['Precio desc'])
            total_p_w = draw.textlength("S/ ", font=f_simbolo) + draw.textlength(p_str, font=f_precio)
            p_x = r_c - (total_p_w / 2)
            draw.text((p_x, y_s + 35), "S/ ", font=f_simbolo, fill=txt_color)
            draw.text((p_x + draw.textlength("S/ ", font=f_simbolo), y_s), p_str, font=f_precio, fill=txt_color)
            draw.text((r_c, y_s + 125), str(row['SKU']), font=f_sku, fill=txt_color, anchor="mt")
            draw.text((60, 1860), "CONDICIONES GENERALES: ", font=f_leg_bold, fill=txt_color)
            draw.text((60 + draw.textlength("CONDICIONES GENERALES: ", font=f_leg_bold), 1863), str(row['Legales']), font=f_leg_reg, fill=txt_color)
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
