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

# --- CONFIGURACIÓN DE RUTAS ---
USER_GH = "analyticsdatajg2025-cmd"
REPO_GH = "GITHUB_CATALOGOS_CONECTA"
RAW_URL = f"https://raw.githubusercontent.com/{USER_GH}/{REPO_GH}/main/output/"

def quitar_fondo_blanco(img):
    return img

def draw_justified_text(draw, text, font, y_start, x_start, x_end, fill, line_spacing=5, prefix_width=0):
    available_w = x_end - x_start
    words = text.split()
    lines = []
    current_line = []
    current_w = prefix_width 

    for word in words:
        word_w = draw.textlength(word + " ", font=font)
        if current_w + word_w <= available_w:
            current_line.append(word)
            current_w += word_w
        else:
            lines.append(current_line)
            current_line = [word]
            current_w = draw.textlength(word + " ", font=font)
    lines.append(current_line)

    y = y_start
    normal_space_w = draw.textlength(" ", font=font)

    for i, line_words in enumerate(lines):
        if not line_words: continue
        line_x_start = x_start + (prefix_width if i == 0 else 0)
        line_available_w = available_w - (prefix_width if i == 0 else 0)
        line_text = " ".join(line_words)
        total_text_w = sum(draw.textlength(w, font=font) for w in line_words)
        num_spaces = len(line_words) - 1
        
        if num_spaces > 0:
            target_space_w = (line_available_w - total_text_w) / num_spaces
        else:
            target_space_w = 0

        if i == len(lines) - 1 or len(line_words) <= 1 or target_space_w > (normal_space_w * 2.5):
            draw.text((line_x_start, y), line_text, font=font, fill=fill)
        else:
            curr_x = line_x_start
            for word in line_words:
                draw.text((curr_x, y), word, font=font, fill=fill)
                curr_x += draw.textlength(word, font=font) + target_space_w
        y += font.getbbox("Ay")[3] + line_spacing
        
def get_sheets_data():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_info = json.loads(os.environ.get('GOOGLE_CREDENTIALS'))
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key("1PmvCyC3d0VvvZSdvWM73NYusrYevVYtRzVs2gbxjw1M")
    data = pd.DataFrame(sheet.worksheet("Hoja 1").get_all_records())
    data.columns = [c.strip() for c in data.columns]
    res_sheet = sheet.worksheet("Resultados")
    v_act = res_sheet.get_all_values()
    viejos = {r[1].strip().upper() for r in v_act[1:] if len(r) > 1}
    return data, res_sheet, viejos

def generar_diseno(data_input, color_version="AMARILLO"):
    is_flyer = isinstance(data_input, pd.DataFrame)
    row = data_input.iloc[0] if is_flyer else data_input
    tipo, formato = str(row['Tipo de diseño']).strip(), str(row['Formato']).upper().strip()
    path_fonts, path_fondos = "TIPOGRAFIA/LC", f"FONDOS/LC/{tipo}"
    
    txt_c = (0,0,0) if color_version == "AMARILLO" else (255,255,255)
    border_c = (254, 215, 0) if color_version == "AMARILLO" else (10, 6, 60)

    try:
        precio_val = "{:,}".format(int(float(row['Precio desc'])))
    except:
        precio_val = str(row['Precio desc'])

    fname_base = f"LC - {tipo} - {'FLYER' if formato == 'FLYER' else formato}"
    full_p = next((os.path.join(path_fondos, f"{v}{e}") for v in [f"{fname_base} FONDO {color_version}", f"{fname_base} {color_version}", fname_base] for e in [".png", ".jpg", ".PNG", ".JPG"] if os.path.exists(os.path.join(path_fondos, f"{v}{e}"))), None)
    if not full_p: return None
    img = Image.open(full_p).convert("RGB"); draw = ImageDraw.Draw(img)

    try:
        f_f = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 24)
        if formato == "STORY":
            f_m = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 53); f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 32); f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 106); f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 42); f_s_ind = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 18); f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 14)
        elif formato == "PPL":
            f_m = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 43); f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 23); f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 85); f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 36); f_s_ind = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 14); f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 13)
        elif formato == "FLYER":
            f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 60); f_s_fly = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 13); f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 16); f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 18); f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 24) 
        else:
            f_m = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 34); f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 20); f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 75); f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 30); f_s_ind = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 13); f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 9)
    except: 
        f_m = f_p = f_pv = f_ps = f_s_ind = f_s_fly = f_f = f_l = ImageFont.load_default()

    if formato == "FLYER":
        f_txt = str(row['Fecha_disponibilidad_flyer']).upper()
        wf = draw.textlength(f_txt, font=f_f)
        x_fecha = 64 
        # AJUSTE: Color Negro para fecha y contorno
        negro_fecha = (0, 0, 0)
        draw.rounded_rectangle([x_fecha, 235, x_fecha+wf+35, 285], radius=10, outline=negro_fecha, width=3)
        draw.text((x_fecha+(wf+35)//2, 260), f_txt, font=f_f, fill=negro_fecha, anchor="mm")
        
        azul_oscuro = (10, 6, 60)
        num_productos = len(data_input)
        if num_productos <= 6:
            box_w, box_h = 456, 456; img_size = 338; gap_y = 30; y_offset_img = 20
        else:
            box_w, box_h = 456, 375; img_size = 250; gap_y = 15; y_offset_img = 10
        for i, (idx, p) in enumerate(data_input.iterrows()):
            if i >= 8: break
            try: p_val = "{:,}".format(int(float(p['Precio desc'])))
            except: p_val = str(p['Precio desc'])
            xp = 64 + (i % 2) * (box_w + 40); yp = 340 + (i // 2) * (box_h + gap_y)
            draw.rounded_rectangle([xp, yp, xp+box_w, yp+box_h], radius=15, fill=(255,255,255), outline=border_c, width=2)
            try:
                pi_url = p['Foto del producto calado']; pi = Image.open(BytesIO(requests.get(pi_url).content)).convert("RGBA"); pi.thumbnail((img_size, img_size), Image.Resampling.LANCZOS)
                img.paste(pi, (int(xp + (box_w - pi.width) // 2), int(yp + y_offset_img)), pi)
            except: pass
            cl, cr = xp + 114, xp + 342; y_marca_prod = yp + box_h - 86 
            f_m_fly = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 20 if len(p['Marca']) < 12 else 16)
            draw.text((cl, y_marca_prod), p['Marca'], font=f_m_fly, fill=azul_oscuro, anchor="mm")
            ny = y_marca_prod + 25 
            for ln in textwrap.wrap(p['Nombre del producto'], width=18)[:2]:
                draw.text((cl, ny), ln, font=f_p, fill=azul_oscuro, anchor="mm"); ny += 20
            y_precio = yp + box_h - 57; tw_p = draw.textlength("S/", font=f_ps) + draw.textlength(p_val, font=f_pv) + 8; px_inicio = cr - tw_p // 2
            draw.text((px_inicio, y_precio), "S/", font=f_ps, fill=azul_oscuro, anchor="lm")
            draw.text((px_inicio + draw.textlength("S/", font=f_ps) + 8, y_precio), p_val, font=f_pv, fill=azul_oscuro, anchor="lm")
            draw.text((cr, y_precio + 35), str(p['SKU']), font=f_s_fly, fill=azul_oscuro, anchor="mm")
        
        # AJUSTE: Legales en Negro para Flyer
        y_legales_fijo = 1815; f_l_bold = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 16); tit_legal = "CONDICIONES GENERALES: "; cuerpo_legal = str(row['Legales']); ancho_negrita = draw.textlength(tit_legal, font=f_l_bold)
        color_negro = (0, 0, 0)
        draw.text((64, y_legales_fijo), tit_legal, font=f_l_bold, fill=color_negro)
        draw_justified_text(draw, cuerpo_legal, f_l, y_legales_fijo, 64, 1016, color_negro, line_spacing=2, prefix_width=ancho_negrita)
    else:
        # Lógica para otros formatos se mantiene igual...
        pi = Image.open(BytesIO(requests.get(row['Foto del producto calado']).content)).convert("RGBA")
        if formato == "DISPLAY":
            pi.thumbnail((483, 483)); img.paste(pi, (423, 25), pi); cx, ny = 255, 245 
            draw.text((cx, 195), row['Marca'], font=f_m, fill=txt_c, anchor="mt")
            lineas_nombre = textwrap.wrap(row['Nombre del producto'], width=22)[:2]
            for l in lineas_nombre: draw.text((cx, ny), l, font=f_p, fill=txt_c, anchor="mt"); ny += 27 
            tw = draw.textlength("S/", font=f_ps) + draw.textlength(precio_val, font=f_pv) + 15; px = cx - tw//2
            draw.text((px, ny + 55), "S/ ", font=f_ps, fill=txt_c, anchor="lm"); draw.text((px + draw.textlength("S/ ", font=f_ps) + 15, ny + 55), precio_val, font=f_pv, fill=txt_c, anchor="lm")
            draw.text((cx, ny + 100), str(row['SKU']), font=f_s_ind, fill=txt_c, anchor="mt")
            f_l_bold = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 9); tit_legal = "CONDICIONES GENERALES: "; cuerpo_legal = str(row['Legales']); ancho_negrita = draw.textlength(tit_legal, font=f_l_bold)
            draw.text((40, 485), tit_legal, font=f_l_bold, fill=txt_c)
            draw_justified_text(draw, cuerpo_legal, f_l, y_start=485, x_start=40, x_end=960, fill=txt_c, line_spacing=2, prefix_width=ancho_negrita)
        elif formato == "STORY":
            pi = pi.resize((845, 845), Image.Resampling.LANCZOS); img.paste(pi, (140, 630), pi); cx_textos, anchor_y_textos = 150, 1482 
            draw.text((cx_textos, anchor_y_textos), row['Marca'], font=f_m, fill=txt_c, anchor="lt"); ny = anchor_y_textos + 65 
            lineas_nombre = textwrap.wrap(row['Nombre del producto'], width=22)[:2]
            for l in lineas_nombre: draw.text((cx_textos, ny), l, font=f_p, fill=txt_c, anchor="lt"); ny += 40 
            anchor_y_precio, p_v, espacio_entre_simbolo = 1540, precio_val, 20
            tw = draw.textlength("S/", font=f_ps) + draw.textlength(p_v, font=f_pv) + espacio_entre_simbolo; px_bloque_completo = 810 - tw//2
            draw.text((px_bloque_completo, anchor_y_precio), "S/", font=f_ps, fill=txt_c, anchor="ls"); px_numero = px_bloque_completo + draw.textlength("S/", font=f_ps) + espacio_entre_simbolo; draw.text((px_numero, anchor_y_precio), p_v, font=f_pv, fill=txt_c, anchor="ls")
            draw.text((810, anchor_y_precio + 40), str(row['SKU']), font=f_s_ind, fill=txt_c, anchor="mt") 
            f_l_bold = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 14); tit_legal = "CONDICIONES GENERALES: "; cuerpo_legal = str(row['Legales']); ancho_negrita = draw.textlength(tit_legal, font=f_l_bold); draw.text((65, 1802), tit_legal, font=f_l_bold, fill=txt_c)
            draw_justified_text(draw, cuerpo_legal, f_l, y_start=1802, x_start=65, x_end=1015, fill=txt_c, line_spacing=2, prefix_width=ancho_negrita)
        elif formato == "PPL":
            pi.thumbnail((847, 650), Image.Resampling.LANCZOS); canvas_width = 1080; px_centrado = (canvas_width - pi.width) // 2; py_posicion = 220; img.paste(pi, (px_centrado, py_posicion), pi); y_base_alineacion, y_precio = 850, 865 
            p_v, w_simbolo, w_monto, espacio_interno = precio_val, draw.textlength("S/", font=f_ps), draw.textlength(precio_val, font=f_pv), 15
            tw_precio = w_simbolo + w_monto + espacio_interno; eje_x_derecha = 820; px_inicio_bloque = eje_x_derecha - tw_precio // 2 
            draw.text((px_inicio_bloque, y_precio), "S/", font=f_ps, fill=txt_c, anchor="ls"); px_numero = px_inicio_bloque + w_simbolo + espacio_interno; draw.text((px_numero, y_precio), p_v, font=f_pv, fill=txt_c, anchor="ls"); draw.text((eje_x_derecha, y_precio + 30), str(row['SKU']), font=f_s_ind, fill=txt_c, anchor="mt") 
            cx = 200; draw.text((cx, y_base_alineacion), row['Marca'], font=f_m, fill=txt_c, anchor="ls"); ny = y_base_alineacion + 10 
            lineas_nombre = textwrap.wrap(row['Nombre del producto'], width=25)[:2]
            for l in lineas_nombre: draw.text((cx, ny), l, font=f_p, fill=txt_c, anchor="lt"); ny += 30
            f_l_bold = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 13); tit_legal = "CONDICIONES GENERALES: "; cuerpo_legal = str(row['Legales']); ancho_negrita = draw.textlength(tit_legal, font=f_l_bold); draw.text((50, 990), tit_legal, font=f_l_bold, fill=txt_c)
            draw_justified_text(draw, cuerpo_legal, f_l, y_start=990, x_start=50, x_end=1030, fill=txt_c, line_spacing=2, prefix_width=ancho_negrita)

    sku_limpio = str(row['SKU'] or row['ID_Flyer']).replace("/", "-").replace("\\", "-")
    fname = f"{sku_limpio}_{formato}_{color_version}.jpg"
    img.save(f"output/{fname}", quality=95); return f"{RAW_URL}{fname}"

# --- BUCLE DE EJECUCIÓN PRINCIPAL (CON ACUMULACIÓN DE FILAS) ---
data, res_sheet, viejos = get_sheets_data()
os.makedirs('output', exist_ok=True)
h_lima = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")
archivos_generados = 0 
filas_para_google = [] 

print(f"DEBUG: Filas detectadas en el Excel: {len(data)}")

for idx, row in data.iterrows():
    f_v = str(row['Formato']).upper().strip()
    if f_v in ["FLYER", "", "0"]: continue
    
    versiones = ["AMARILLO", "AZUL"] if str(row['Tipo de diseño']).strip() == "DSCTOS POWER" else ["AMARILLO"]
    for c in versiones:
        sku_val = str(row['SKU']).replace("/", "-").replace("\\", "-")
        llave = f"{sku_val}_{f_v}_{c}".upper()
        if llave not in viejos:
            print(f"🎨 Generando pieza nueva: {llave}")
            url = generar_diseno(row, c)
            if url: 
                filas_para_google.append([h_lima, llave, row['Tipo de diseño'], f_v, c, url])
                archivos_generados += 1

fly_g = data[data['Formato'].astype(str).str.upper().str.strip() == "FLYER"]
for id_f, group in fly_g.groupby('ID_Flyer'):
    if str(id_f) in ["0", "0.0", ""]: continue
    versiones = ["AZUL", "AMARILLO"] if str(group.iloc[0]['Tipo de diseño']).strip() == "DSCTOS POWER" else ["AMARILLO"]
    for c in versiones:
        llave = f"{id_f}_FLYER_{c}".upper()
        if llave not in viejos:
            print(f"🎨 Generando Flyer nuevo: {llave}")
            url = generar_diseno(group, c)
            if url: 
                filas_para_google.append([h_lima, llave, group.iloc[0]['Tipo de diseño'], "FLYER", c, url])
                archivos_generados += 1

if filas_para_google:
    res_sheet.append_rows(filas_para_google)
    print(f"✅ Éxito: Se registraron {len(filas_para_google)} piezas nuevas.")

if archivos_generados == 0:
    print("⚠️ No se generaron archivos nuevos.")
    with open("last_run.txt", "w") as f:
        f.write(f"Sin cambios: {h_lima}")