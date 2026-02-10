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

def draw_justified_text(draw, text, font, y_start, x_start, x_end, fill):
    """Dibuja texto legal justificado de margen a margen."""
    # Aseguramos que siempre empiece con CONDICIONES GENERALES
    if not text.startswith("CONDICIONES GENERALES"):
        text = "CONDICIONES GENERALES: " + text
        
    lines = textwrap.wrap(text, width=135 if (x_end - x_start) > 600 else 65)
    line_height = font.getbbox("Ay")[3] + 4
    
    for i, line in enumerate(lines):
        words = line.split()
        # Si es la última línea o solo hay una palabra, alinear a la izquierda
        if i == len(lines) - 1 or len(words) <= 1:
            draw.text((x_start, y_start), line, font=font, fill=fill)
        else:
            # Justificación: distribuir el espacio sobrante entre las palabras
            total_words_w = sum(draw.textlength(w, font=font) for w in words)
            space_width = ((x_end - x_start) - total_words_w) / (len(words) - 1)
            x_cursor = x_start
            for word in words:
                draw.text((x_cursor, y_start), word, font=font, fill=fill)
                x_cursor += draw.textlength(word, font=font) + space_width
        y_start += line_height

def draw_efe_preciador(draw, x_center, y_center, text_s, text_price, f_ps, f_pv, scale=1.0, tracking=-2):
    """Preciador con S/ pequeño y kerning (tracking) controlado."""
    # Cálculo de ancho del número con tracking
    num_w = 0
    for char in text_price:
        num_w += draw.textlength(char, font=f_pv) + tracking
    num_w -= tracking # Quitar último tracking
    
    sym_w = draw.textlength(text_s, font=f_ps)
    gap = 6 * scale
    full_w = sym_w + gap + num_w
    
    h = int(110 * scale)
    draw.rounded_rectangle([x_center - full_w//2 - 20, y_center - h//2, x_center + full_w//2 + 20, y_center + h//2], 
                           radius=15, fill="#FFA002")
    
    tx = x_center - full_w//2
    # Dibujar S/ (Siempre menor)
    draw.text((tx, y_center), text_s, font=f_ps, fill=(255,255,255), anchor="lm")
    
    # Dibujar Precio con tracking
    curr_x = tx + sym_w + gap
    for char in text_price:
        draw.text((curr_x, y_center), char, font=f_pv, fill=(255,255,255), anchor="lm")
        curr_x += draw.textlength(char, font=f_pv) + tracking

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
    tienda = str(row.get('Tienda', 'LC')).strip().upper()
    tipo = str(row['Tipo de diseño']).strip().upper()
    formato = str(row['Formato']).upper().strip()
    path_fonts, path_fondos = f"TIPOGRAFIA/{tienda}", f"FONDOS/{tienda}/{tipo}"
    txt_c = (255,255,255) if tienda == "EFE" else (0,0,0)

    f_names = [f"{tienda} - {tipo} - {formato}", f"{tienda} - REPOWER {tipo} - {formato}"]
    full_p = next((os.path.join(path_fondos, f"{v}{e}") for v in f_names for e in [".jpg", ".png", ".JPG"] if os.path.exists(os.path.join(path_fondos, f"{v}{e}"))), None)
    if not full_p: return None
    img = Image.open(full_p).convert("RGB"); draw = ImageDraw.Draw(img)

    # --- CONFIGURACIÓN DE FUENTES ---
    try:
        # Precios base
        p_size = 90
        s_size = 35
        if formato == "DISPLAY": 
            p_size = 70; s_size = 30
        elif formato == "STORY": 
            p_size = 100; s_size = 40
        
        f_m = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 44 if formato == "STORY" else 32)
        f_p = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 30 if formato == "STORY" else 20)
        f_pv = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", p_size)
        f_ps = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", s_size)
        f_s_ind = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 18 if formato == "STORY" else 15)
        f_l = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 10) 
        f_f = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 26)
    except: f_m = f_p = f_pv = f_ps = f_s_ind = f_l = f_f = ImageFont.load_default()

    if formato == "FLYER":
        f_txt = str(row['Fecha_disponibilidad_flyer']).upper()
        wf = draw.textlength(f_txt, font=f_f)
        draw.text((540, 260), f_txt, font=f_f, fill=(255,255,255), anchor="mm")

        box_h = 330 if len(data_input) > 6 else 450
        for i, (idx, p) in enumerate(data_input.iterrows()):
            if i >= 8: break
            xp, yp = 65+(i%2)*495, 345+(i//2)*(box_h+12)
            
            # Insertar Imagen de Producto en Flyer
            try:
                pi_res = requests.get(p['Foto del producto calado'], timeout=10)
                pi_fly = Image.open(BytesIO(pi_res.content)).convert("RGBA")
                pi_fly.thumbnail((250, 250))
                img.paste(pi_fly, (xp + 240 - pi_fly.width//2, yp + 120 - pi_fly.height//2), pi_fly)
            except: pass

            if tienda == "EFE":
                cx_l = xp + 125
                draw.text((cx_l, yp+box_h-115), p['Marca'], font=f_m, fill=(0,0,0), anchor="mm")
                ny = yp+box_h-90
                for ln in textwrap.wrap(p['Nombre del producto'], width=18)[:2]:
                    draw.text((cx_l, ny), ln, font=f_p, fill=(0,0,0), anchor="mm"); ny += 24
                
                if "EFERTON" in tipo: 
                    draw_efe_preciador(draw, xp+345, yp+box_h-75, "S/", str(p['Precio desc']), f_ps, f_pv, scale=0.6, tracking=-3)
                else:
                    # Precio normal flyer con S/ pequeño
                    w_total = draw.textlength("S/", font=f_ps) + 5 + draw.textlength(str(p['Precio desc']), font=f_pv)
                    curr_x = (xp + 345) - w_total // 2
                    draw.text((curr_x, yp+box_h-75), "S/", font=f_ps, fill="#FFA002", anchor="lm")
                    draw.text((curr_x + draw.textlength("S/", font=f_ps) + 5, yp+box_h-75), str(p['Precio desc']), font=f_pv, fill="#FFA002", anchor="lm")
        
        draw_justified_text(draw, str(row['Legales']), f_l, 1835, 65, 1015, (255,255,255))

    else:
        headers = {'User-Agent': 'Mozilla/5.0'}
        pi_res = requests.get(row['Foto del producto calado'], headers=headers, timeout=10)
        pi = Image.open(BytesIO(pi_res.content)).convert("RGBA")
        
        if formato == "PPL":
            if "EFERTON" in tipo:
                pi.thumbnail((580, 580)); img.paste(pi, (500-pi.width//2, 525-pi.height//2), pi) # -20px imagen
                ay = 830
                draw.text((160, ay), row['Marca'], font=f_m, fill=(255,255,255), anchor="mm")
                draw_efe_preciador(draw, 840, ay, "S/", str(row['Precio desc']), f_ps, f_pv, scale=0.9, tracking=-3)
                draw_justified_text(draw, str(row['Legales']), f_l, 940, 50, 950, (255,255,255))
            else: # PPL PRECIO IRRESISTIBLE
                pi.thumbnail((583, 583)); img.paste(pi, (510-pi.width//2, 510-pi.height//2), pi)
                ay = 740 # Textos subidos 50px
                draw.text((100, ay), row['Marca'], font=f_m, fill=(255,255,255), anchor="lm")
                # Precios específicos 80pt y 40pt
                f_pv80 = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 80)
                f_ps40 = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 40)
                draw.text((100, ay+80), "S/", font=f_ps40, fill=(255,255,255), anchor="lm")
                draw.text((100 + 65, ay+80), str(row['Precio desc']), font=f_pv80, fill=(255,255,255), anchor="lm")
                draw_justified_text(draw, str(row['Legales']), f_l, 980, 50, 950, (255,255,255)) # Bajado 30px

        elif formato == "STORY":
            pi.thumbnail((900, 900)); img.paste(pi, (540-pi.width//2, 630), pi)
            ay = 1520 # Bajado 20px
            draw.text((270, ay), row['Marca'], font=f_m, fill=(255,255,255), anchor="mm")
            # Precio Story con tracking más apretado
            if "EFERTON" in tipo:
                draw_efe_preciador(draw, 810, ay+20, "S/", str(row['Precio desc']), f_ps, f_pv, scale=1.1, tracking=-4)
            else:
                w_tot = draw.textlength("S/", font=f_ps) + 8 + draw.textlength(str(row['Precio desc']), font=f_pv)
                cx = 810 - w_tot // 2
                draw.text((cx, ay+20), "S/", font=f_ps, fill=(255,255,255), anchor="lm")
                draw.text((cx + draw.textlength("S/", font=f_ps) + 8, ay+20), str(row['Precio desc']), font=f_pv, fill=(255,255,255), anchor="lm")
            draw_justified_text(draw, str(row['Legales']), f_l, 1835, 65, 1015, (255,255,255))

        elif formato == "DISPLAY":
            pi.thumbnail((400, 400))
            if "IRRESISTIBLE" in tipo: img.paste(pi, (502, 70), pi) # -20px izquierda
            else: img.paste(pi, (530, 70), pi)
            
            cx = 265
            if "EFERTON" in tipo:
                draw_efe_preciador(draw, cx, 405, "S/", str(row['Precio desc']), f_ps, f_pv, scale=0.55, tracking=-3)
            else:
                # S/ menor al precio
                w_s = draw.textlength("S/", font=f_ps)
                draw.text((cx-40, 405), "S/", font=f_ps, fill=(255,255,255), anchor="mm")
                draw.text((cx-40 + w_s + 5, 405), str(row['Precio desc']), font=f_pv, fill=(255,255,255), anchor="mm")
            # Legales display (sin justificación extrema por espacio pero con prefijo)
            draw_justified_text(draw, str(row['Legales']), f_l, 450, 40, 480, (255,255,255))

    fname = f"{row['SKU'] or row['ID_Flyer']}_{formato}_{tienda}.jpg"
    img.save(f"output/{fname}", quality=95); return f"{RAW_URL}{fname}"

# --- PROCESO PRINCIPAL ---
data, res_sheet, viejos = get_sheets_data(); os.makedirs('output', exist_ok=True)
h_lima = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")

for idx, row in data.iterrows():
    f_v = str(row['Formato']).upper().strip()
    if f_v in ["FLYER", "", "0"]: continue
    tienda = str(row.get('Tienda', 'LC')).strip().upper()
    llave = f"{row['SKU']}_{f_v}_{tienda}_EFE".upper()
    if llave not in viejos:
        url = generar_diseno(row)
        if url: res_sheet.append_row([h_lima, llave, tienda, row['Tipo de diseño'], f_v, "EFE", url])

fly_g = data[data['Formato'].astype(str).str.upper().str.strip() == "FLYER"]
for id_f, group in fly_g.groupby('ID_Flyer'):
    if str(id_f) in ["0", "0.0", ""]: continue
    llave = f"{id_f}_FLYER_EFE".upper()
    if llave not in viejos:
        url = generar_diseno(group)
        if url: res_sheet.append_row([h_lima, llave, "EFE", group.iloc[0]['Tipo de diseño'], "FLYER", "EFE", url])
