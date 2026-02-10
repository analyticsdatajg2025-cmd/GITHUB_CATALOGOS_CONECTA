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
    """Dibuja texto legal justificado que ocupa de margen a margen."""
    # Asegurar que empiece con CONDICIONES GENERALES en negrita se maneja desde el llamado
    # pero aquí forzamos el wrap y la distribución de espacios.
    lines = textwrap.wrap(text, width=130 if (x_end - x_start) > 600 else 60)
    line_height = font.getbbox("Ay")[3] + 4
    
    for i, line in enumerate(lines):
        words = line.split()
        if i == len(lines) - 1 or len(words) <= 1: # Última línea o una sola palabra: alineada a la izquierda
            draw.text((x_start, y_start), line, font=font, fill=fill)
        else:
            # Distribuir espacios para justificar
            total_words_width = sum(draw.textlength(w, font=font) for w in words)
            space_width = ( (x_end - x_start) - total_words_width) / (len(words) - 1)
            x_cursor = x_start
            for word in words:
                draw.text((x_cursor, y_start), word, font=font, fill=fill)
                x_cursor += draw.textlength(word, font=font) + space_width
        y_start += line_height

def draw_efe_preciador(draw, x_center, y_center, text_s, text_price, f_ps, f_pv, scale=1.0, tracking=-2):
    """Preciador con S/ pequeño y números con kerning ajustable."""
    # El símbolo S/ siempre es menor (ya viene definido en las fuentes pasadas)
    # Tracking negativo para juntar los números
    
    # Dibujar número caracter por caracter para controlar el espaciado (tracking)
    total_num_w = 0
    for char in text_price:
        total_num_w += draw.textlength(char, font=f_pv) + tracking
    total_num_w -= tracking # Quitar el último track
    
    sym_w = draw.textlength(text_s, font=f_ps)
    gap = 5 
    full_w = sym_w + gap + total_num_w
    
    h = int(110 * scale)
    draw.rounded_rectangle([x_center - full_w//2 - 20, y_center - h//2, x_center + full_w//2 + 20, y_center + h//2], 
                           radius=15, fill="#FFA002")
    
    # Dibujar S/
    tx = x_center - full_w//2
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

    # --- DEFINICIÓN DE FUENTES ---
    try:
        if tienda == "EFE":
            # Display ajustes
            if formato == "DISPLAY":
                size_price = 70 if "IRRESISTIBLE" in tipo or "EFERTON" in tipo else 100
                size_s = 30
            else:
                size_price = 99 if formato == "PPL" else (70 if formato == "FLYER" else 100)
                size_s = 40 if formato != "FLYER" else 30
            
            f_m = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 44 if formato == "STORY" else 32)
            f_p = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 30 if formato == "STORY" else 20)
            f_pv = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", size_price)
            f_ps = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", size_s)
            f_s_ind = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 18 if formato == "STORY" else 15)
            f_l = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 10) 
            f_f = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 26)
        else: # LC (Mantenemos lógica pero ajustando S/)
            # ... (Fuentes LC se mantienen igual pero asegurando f_ps < f_pv)
            pass
    except: f_m = f_p = f_pv = f_ps = f_s_ind = f_l = f_f = ImageFont.load_default()

    legal_text = "CONDICIONES GENERALES: " + str(row['Legales'])

    if formato == "FLYER":
        # ... (Lógica de cabecera flyer)
        box_h = 330 if len(data_input) > 6 else 450
        for i, (idx, p) in enumerate(data_input.iterrows()):
            if i >= 8: break
            xp, yp = 65+(i%2)*495, 345+(i//2)*(box_h+12)
            
            # Cargar imagen de producto para Flyer
            try:
                pi_url = p['Foto del producto calado']
                pimg = Image.open(BytesIO(requests.get(pi_url).content)).convert("RGBA")
                pimg.thumbnail((220, 220))
                img.paste(pimg, (xp + 240 - pimg.width//2, yp + 100), pimg)
            except: pass

            if tienda == "EFE":
                # ... (Líneas punteadas)
                cx_l = xp + 125
                draw.text((cx_l, yp+box_h-115), p['Marca'], font=f_m, fill=(0,0,0), anchor="mm")
                # Precios flyer con números más juntos
                if "EFERTON" in tipo: 
                    draw_efe_preciador(draw, xp+345, yp+box_h-75, "S/", str(p['Precio desc']), f_ps, f_pv, scale=0.6, tracking=-3)
                else: 
                    # S/ Manual más pequeño
                    txt_s = "S/"
                    w_s = draw.textlength(txt_s, font=f_ps)
                    draw.text((xp+300, yp+box_h-75), txt_s, font=f_ps, fill="#FFA002", anchor="mm")
                    draw.text((xp+300 + w_s + 5, yp+box_h-75), str(p['Precio desc']), font=f_pv, fill="#FFA002", anchor="mm")
        
        draw_justified_text(draw, legal_text, f_l, 1835, 65, 1015, (255,255,255) if tienda=="EFE" else txt_c)

    else:
        headers = {'User-Agent': 'Mozilla/5.0'}
        pi = Image.open(BytesIO(requests.get(row['Foto del producto calado'], headers=headers).content)).convert("RGBA")
        
        if formato == "PPL":
            if "EFERTON" in tipo:
                pi.thumbnail((580, 580)); img.paste(pi, (500-pi.width//2, 525-pi.height//2), pi) # Bajado 20px
                ay = 830
                # Dibujar textos y precio con tracking
                draw_efe_preciador(draw, 840, ay, "S/", str(row['Precio desc']), f_ps, f_pv, scale=0.9, tracking=-3)
                draw_justified_text(draw, legal_text, f_l, 940, 50, 950, (255,255,255))
            else: # PRECIO IRRESISTIBLE PPL
                pi.thumbnail((583, 583)); img.paste(pi, (510-pi.width//2, 510-pi.height//2), pi)
                ay = 740 # Subido 50px (era 790)
                draw.text((100, ay), row['Marca'], font=f_m, fill=(255,255,255), anchor="lm")
                # Precio ajustado a 80pt y 40pt
                f_pv_ppl = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 80)
                f_ps_ppl = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 40)
                draw.text((100, ay + 100), "S/", font=f_ps_ppl, fill=(255,255,255), anchor="lm")
                draw.text((100 + 60, ay + 100), str(row['Precio desc']), font=f_pv_ppl, fill=(255,255,255), anchor="lm")
                draw_justified_text(draw, legal_text, f_l, 980, 50, 950, (255,255,255)) # Legales bajados 30px

        elif formato == "STORY":
            pi.thumbnail((900, 900)); img.paste(pi, (540-pi.width//2, 630), pi)
            ay = 1520 # Bajado 20px (era 1500)
            draw.text((270, ay), row['Marca'], font=f_m, fill=(255,255,255), anchor="mm")
            # ... Nombres y SKU con ay + 20px ...
            if "EFERTON" in tipo: 
                draw_efe_preciador(draw, 810, ay+20, "S/", str(row['Precio desc']), f_ps, f_pv, scale=1.1, tracking=-4)
            draw_justified_text(draw, legal_text, f_l, 1835, 65, 1015, (255,255,255))

        elif formato == "DISPLAY":
            pi.thumbnail((400, 400))
            if "IRRESISTIBLE" in tipo: 
                img.paste(pi, (502, 70), pi) # Movido 20px a la izquierda (era 522)
            else: img.paste(pi, (530, 70), pi)
            
            # Preciador Display EFERTON más pequeño y números juntos
            if "EFERTON" in tipo:
                draw_efe_preciador(draw, 265, 405, "S/", str(row['Precio desc']), f_ps, f_pv, scale=0.5, tracking=-5)
            else:
                # S/ menor al precio en display normal
                w_s = draw.textlength("S/", font=f_ps)
                draw.text((200, 405), "S/", font=f_ps, fill=(255,255,255), anchor="mm")
                draw.text((200 + w_s + 5, 405), str(row['Precio desc']), font=f_pv, fill=(255,255,255), anchor="mm")

    fname = f"{row['SKU'] or row['ID_Flyer']}_{formato}_{tienda}.jpg"
    img.save(f"output/{fname}", quality=95); return f"{RAW_URL}{fname}"

# --- EJECUCIÓN (Resto del script igual) ---