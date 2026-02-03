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
    
    # Lectura desde Hoja 1
    data = pd.DataFrame(sheet.worksheet("Hoja 1").get_all_records())
    data.columns = [c.strip() for c in data.columns]
    
    res_sheet = sheet.worksheet("Resultados")
    valores_actuales = res_sheet.get_all_values()
    registros_viejos = set()
    if len(valores_actuales) > 1:
        for row in valores_actuales[1:]:
            if len(row) >= 2:
                registros_viejos.add(row[1].strip().upper())
    
    return data, res_sheet, registros_viejos

def generar_diseno(data_input, color_version="AMARILLO"):
    is_flyer = isinstance(data_input, pd.DataFrame)
    row = data_input.iloc[0] if is_flyer else data_input
    
    tipo = str(row['Tipo de diseño']).strip()
    formato = str(row['Formato']).upper().strip()
    path_fonts = "TIPOGRAFIA/LC"
    path_fondos = f"FONDOS/LC/{tipo}"
    
    txt_color = (0,0,0) if color_version == "AMARILLO" else (255,255,255)
    border_color = (254, 215, 0) if color_version == "AMARILLO" else (10, 6, 60) # #FED700 y #0A063C
    date_accent = (0,0,0) if color_version == "AMARILLO" else (255,255,255)

    # Búsqueda dinámica de fondo
    base_name = f"LC - {tipo} - {formato}"
    if formato == "FLYER": base_name = f"LC - {tipo} - FLYER"
    
    full_path_fondo = None
    for var in [f"{base_name} FONDO {color_version}", f"{base_name} {color_version}", base_name]:
        for ex in [".png", ".jpg", ".PNG", ".JPG"]:
            test_p = os.path.join(path_fondos, f"{var}{ex}")
            if os.path.exists(test_p):
                full_path_fondo = test_p; break
        if full_path_fondo: break
    
    if not full_path_fondo: return None
    img = Image.open(full_path_fondo).convert("RGB"); draw = ImageDraw.Draw(img)

    # FUENTES (HurmeGeometricSans1)
    try:
        f_m = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 35) # Marca reducida
        f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 20) # Producto
        f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 75) # Precio Valor
        f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 35) # S/ Pequeño
        f_s = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 18) # SKU aumentado
        f_f = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 26)
        f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 11)
    except: f_m = f_p = f_pv = f_ps = f_s = f_f = f_l = ImageFont.load_default()

    if formato == "FLYER":
        try:
            # 1. Fecha dinámica (Cuadro redondeado)
            fecha_txt = str(row['Fecha_disponibilidad_flyer']).upper()
            wf = draw.textlength(fecha_txt, font=f_f)
            draw.rounded_rectangle([75, 235, 75+wf+40, 285], radius=10, outline=date_accent, width=3)
            draw.text((75+(wf+40)//2, 260), fecha_txt, font=f_f, fill=date_accent, anchor="mm")
            # 2. Cuadrícula dinámica
            box_h = 330 if len(data_input) > 6 else 450
            for i, (idx, p) in enumerate(data_input.iterrows()):
                if i >= 8: break
                xp, yp = 65+(i%2)*495, 345+(i//2)*(box_h+12)
                draw.rounded_rectangle([xp, yp, xp+455, yp+box_h], radius=15, fill=(255,255,255), outline=border_color, width=2)
                pi = quitar_fondo_blanco(Image.open(BytesIO(requests.get(p['Foto del producto calado']).content)))
                pi.thumbnail((box_h-140, box_h-170)); img.paste(pi, (int(xp+(455-pi.width)//2), int(yp+20)), pi)
                cl, cr = xp+115, xp+345
                draw.text((cl, yp+box_h-100), p['Marca'], font=f_m, fill=(0,0,0), anchor="mm")
                ny = yp+box_h-65
                for ln in textwrap.wrap(p['Nombre del producto'], width=15)[:2]:
                    draw.text((cl, ny), ln, font=f_p, fill=(0,0,0), anchor="mm"); ny += 22
                ps_txt, pv_val = str(p['Precio desc']), draw.textlength("S/", font=f_ps)
                px = cr - (pv_val + draw.textlength(ps_txt, font=f_pv))//2
                draw.text((px, yp+box_h-75), "S/", font=f_ps, fill=(0,0,0), anchor="lm")
                draw.text((px+pv_val+5, yp+box_h-75), ps_txt, font=f_pv, fill=(0,0,0), anchor="lm")
                draw.text((cr, yp+box_h-25), str(p['SKU']), font=f_s, fill=(100,100,100), anchor="mm")
            draw.text((65, 1845), textwrap.fill("CONDICIONES GENERALES: "+str(row['Legales']), width=115), font=f_l, fill=txt_color)
        except: return None

    else:
        # Lógica mejorada para STORY, DISPLAY y PPL
        try:
            pi = quitar_fondo_blanco(Image.open(BytesIO(requests.get(row['Foto del producto calado']).content)))
            if formato == "DISPLAY":
                pi.thumbnail((440, 440)); img.paste(pi, (530, 45), pi); cx, ny = 265, 235
                draw.text((cx, 185), row['Marca'], font=f_m, fill=txt_color, anchor="mt")
                for l in textwrap.wrap(row['Nombre del producto'], width=22):
                    draw.text((cx, ny), l, font=f_p, fill=txt_color, anchor="mt"); ny += 25
                px = cx - (draw.textlength("S/ ", font=f_ps) + draw.textlength(str(row['Precio desc']), font=f_pv))//2
                draw.text((px, ny+45), "S/ ", font=f_ps, fill=txt_color, anchor="lm")
                draw.text((px+draw.textlength("S/ ", font=f_ps), ny+45), str(row['Precio desc']), font=f_pv, fill=txt_color, anchor="lm")
                draw.text((cx, ny+105), str(row['SKU']), font=f_s, fill=txt_color, anchor="mt")
                draw.text((40, 470), textwrap.fill("CONDICIONES GENERALES: "+str(row['Legales']), width=105), font=f_l, fill=txt_color)
            elif formato == "STORY":
                pi.thumbnail((750, 750)); img.paste(pi, (540-pi.width//2, 650), pi)
                draw.text((270, 1420), row['Marca'], font=f_m, fill=txt_color, anchor="mt"); ny = 1475
                for l in textwrap.wrap(row['Nombre del producto'], width=20):
                    draw.text((270, ny), l, font=f_p, fill=txt_color, anchor="mt"); ny += 30
                px = 810 - (draw.textlength("S/ ", font=f_ps) + draw.textlength(str(row['Precio desc']), font=f_pv))//2
                draw.text((px, 1475), "S/ ", font=f_ps, fill=txt_color, anchor="mm")
                draw.text((px+50, 1475), str(row['Precio desc']), font=f_pv, fill=txt_color, anchor="mm")
                draw.text((810, 1550), str(row['SKU']), font=f_s, fill=txt_color, anchor="mm")
                draw.text((65, 1850), textwrap.fill("CONDICIONES GENERALES: "+str(row['Legales']), width=110), font=f_l, fill=txt_color)
            elif formato == "PPL":
                pi.thumbnail((450, 450)); img.paste(pi, (500-pi.width//2, 480-pi.height//2), pi)
                draw.text((275, 760), row['Marca'], font=f_m, fill=txt_color, anchor="mt"); ny = 810
                for l in textwrap.wrap(row['Nombre del producto'], width=22):
                    draw.text((275, ny), l, font=f_p, fill=txt_color, anchor="mt"); ny += 28
                px = 735 - (draw.textlength("S/ ", font=f_ps) + draw.textlength(str(row['Precio desc']), font=f_pv))//2
                draw.text((px, 810), "S/ ", font=f_ps, fill=txt_color, anchor="mm")
                draw.text((px+50, 810), str(row['Precio desc']), font=f_pv, fill=txt_color, anchor="mm")
                draw.text((735, 875), str(row['SKU']), font=f_s, fill=txt_color, anchor="mm")
                draw.text((45, 945), textwrap.fill("CONDICIONES GENERALES: "+str(row['Legales']), width=115), font=f_l, fill=txt_color)
        except Exception as e:
            print(f"Error ind: {e}"); return None

    fname = f"{row['SKU'] or row['ID_Flyer']}_{formato}_{color_version}.jpg"
    img.save(f"output/{fname}", quality=95); return f"{RAW_URL}{fname}"

# --- EJECUCIÓN ---
data, res_sheet, viejos = get_sheets_data(); os.makedirs('output', exist_ok=True)
h_lima = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")
for idx, row in data.iterrows():
    f_val = str(row['Formato']).upper().strip()
    if f_val in ["FLYER", "", "0"]: continue
    for c in (["AMARILLO", "AZUL"] if str(row['Tipo de diseño']).strip() == "DSCTOS POWER" else ["AMARILLO"]):
        llave = f"{row['SKU']}_{f_val}_{c}".upper()
        if llave not in viejos:
            url = generar_diseno(row, c)
            if url: res_sheet.append_row([h_lima, llave, row['Tipo de diseño'], f_val, c, url])
fly_g = data[data['Formato'].astype(str).str.upper().str.strip() == "FLYER"]
for id_f, group in fly_g.groupby('ID_Flyer'):
    if str(id_f) in ["0", "0.0", ""]: continue
    for c in (["AZUL", "AMARILLO"] if str(group.iloc[0]['Tipo de diseño']).strip() == "DSCTOS POWER" else ["AMARILLO"]):
        llave = f"{id_f}_FLYER_{c}".upper()
        if llave not in viejos:
            url = generar_diseno(group, c)
            if url: res_sheet.append_row([h_lima, llave, group.iloc[0]['Tipo de diseño'], "FLYER", c, url])