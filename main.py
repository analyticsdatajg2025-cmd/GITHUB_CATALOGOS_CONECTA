# Importación de librerías para sistema, datos, red, imágenes y texto
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

def draw_justified_text(draw, text, font, y_start, x_start, x_end, fill, line_spacing_offset=0, force_justify=False):
    prefix = "CONDICIONES GENERALES: "
    if text.startswith("CONDICIONES GENERALES"):
        text = text.replace("CONDICIONES GENERALES:", "").strip()
    
    try:
        font_path = font.path.replace("Regular", "SemiBold")
        font_bold = ImageFont.truetype(font_path, font.size)
    except:
        font_bold = font

    container_width = x_end - x_start
    full_text = prefix + text
    words = full_text.split()
    
    lines = []
    current_line = []
    current_width = 0
    space_w = draw.textlength(" ", font=font)

    for word in words:
        is_bold = (len(lines) == 0 and len(current_line) <= 1)
        word_font = font_bold if is_bold else font
        word_w = draw.textlength(word, font=word_font)

        if current_width + word_w <= container_width:
            current_line.append(word)
            current_width += word_w + space_w
        else:
            lines.append(current_line)
            current_line = [word]
            current_width = word_w + space_w
    if current_line:
        lines.append(current_line)

    line_height = font.getbbox("Ay")[3] + line_spacing_offset

    for i, line_words in enumerate(lines):
        if not line_words: continue
        is_last_line = (i == len(lines) - 1)
        line_pixels = sum(draw.textlength(w, font=font_bold if (i==0 and j<=1) else font) for j, w in enumerate(line_words))
        too_empty = line_pixels < (container_width * 0.7)

        if is_last_line or too_empty or not force_justify:
            x_cursor = x_start
            for j, word in enumerate(line_words):
                current_font = font_bold if (i == 0 and j <= 1) else font
                draw.text((x_cursor, y_start), word, font=current_font, fill=fill)
                x_cursor += draw.textlength(word, font=current_font) + space_w
        else:
            total_words_w = sum(draw.textlength(w, font=font_bold if (i == 0 and j <= 1) else font) for j, w in enumerate(line_words))
            dynamic_space = (container_width - total_words_w) / (len(line_words) - 1)
            x_cursor = x_start
            for j, word in enumerate(line_words):
                current_font = font_bold if (i == 0 and j <= 1) else font
                draw.text((x_cursor, y_start), word, font=current_font, fill=fill)
                x_cursor += draw.textlength(word, font=current_font) + dynamic_space
        y_start += line_height

def draw_dotted_line(draw, start, end, fill, width=2, gap=8):
    curr_x, curr_y = start
    dest_x, dest_y = end
    dx, dy = dest_x - curr_x, dest_y - curr_y
    dist = (dx**2 + dy**2)**0.5
    if dist == 0: return
    sx, sy = dx/dist, dy/dist
    for i in range(0, int(dist), gap * 2):
        s = (curr_x + sx * i, curr_y + sy * i)
        e = (curr_x + sx * (i + gap), curr_y + sy * (i + gap))
        draw.line([s, e], fill=fill, width=width)

def draw_efe_preciador(draw, x_center, y_center, text_s, text_price, f_ps, f_pv, scale=1.0, tracking=-2, padding_h=20):
    num_w = sum(draw.textlength(char, font=f_pv) + tracking for char in text_price) - tracking 
    sym_w = draw.textlength(text_s, font=f_ps)
    gap = 8 * scale 
    full_w = sym_w + gap + num_w
    h = int(f_pv.size * 1.2 * scale) 
    p_h = padding_h * scale
    draw.rounded_rectangle([x_center - full_w//2 - p_h, y_center - h//2, x_center + full_w//2 + p_h, y_center + h//2], radius=15, fill="#FFA002")
    tx = x_center - full_w//2
    draw.text((tx, y_center), text_s, font=f_ps, fill=(255,255,255), anchor="lm")
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
    try:
        precio_val = "{:,}".format(int(float(row['Precio desc'])))
    except:
        precio_val = str(row['Precio desc'])
    path_fonts, path_fondos = f"TIPOGRAFIA/{tienda}", f"FONDOS/{tienda}/{tipo}"
    f_names = [f"{tienda} - {tipo} - {formato}", f"{tienda} - REPOWER {tipo} - {formato}"]
    full_p = next((os.path.join(path_fondos, f"{v}{e}") for v in f_names for e in [".jpg", ".png", ".JPG"] if os.path.exists(os.path.join(path_fondos, f"{v}{e}"))), None)
    if not full_p: return None
    img = Image.open(full_p).convert("RGB"); draw = ImageDraw.Draw(img)
    try:
        p_size = 90; s_size = 35; l_size = 10
        if formato == "DISPLAY": p_size = 60; s_size = 30; l_size = 8
        elif formato == "STORY": p_size = 100; s_size = 40
        elif formato == "FLYER": p_size = 50; s_size = 25
        f_m = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 44 if formato == "STORY" else 32)
        f_p = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 30 if formato == "STORY" else 20)
        f_pv = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", p_size)
        f_ps = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", s_size)
        f_s_ind = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 18 if formato == "STORY" else 15)
        f_l = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", l_size)
        f_f = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 26)
    except: f_m = f_p = f_pv = f_ps = f_s_ind = f_l = f_f = ImageFont.load_default()

    if formato == "FLYER":
        f_txt = str(row['Fecha_disponibilidad_flyer']).upper()
        # AJUSTE: Tamaño de fuente aumentado en 3 unidades y posición fija X=355, Y=275
        f_f_semibold = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 26)
        draw.text((355, 275), f_txt, font=f_f_semibold, fill=(255,255,255), anchor="lm")
        
        num_prod = len(data_input)
        y_limit_top, y_limit_bottom = 350, 1757
        available_h = y_limit_bottom - y_limit_top
        if num_prod > 6:
            rows, box_h, img_size_w, img_size_h, preciador_scale = 4, 340, 350, 220, 0.45
        else:
            rows, box_h, img_size_w, img_size_h, preciador_scale = 3, 430, 434, 292, 0.55
        total_content_h = (rows * box_h) + ((rows - 1) * 12)
        y_centering_offset = (available_h - total_content_h) // 2
        current_y_top = y_limit_top + y_centering_offset
        for i, (idx, p) in enumerate(data_input.iterrows()):
            if i >= 8: break
            xp, yp = 65 + (i % 2) * 495, current_y_top + (i // 2) * (box_h + 12)
            try:
                url_foto = p.get('Foto del producto calado') or p.get('Foto')
                if url_foto:
                    pi_fly = Image.open(BytesIO(requests.get(url_foto, timeout=10).content)).convert("RGBA")
                    pi_fly.thumbnail((img_size_w, img_size_h))
                    img.paste(pi_fly, (int(xp + 240 - pi_fly.width // 2), int(yp + 20)), pi_fly)
            except: pass
            cx_col1, cx_col2 = xp + 125, xp + 345
            f_m_flyer = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 28)
            draw.text((cx_col1, yp + box_h - 115), p['Marca'], font=f_m_flyer, fill=(0,0,0), anchor="mm")
            y_n = yp + box_h - 85
            for line in textwrap.wrap(str(p['Nombre del producto']), width=18)[:4]: 
                draw.text((cx_col1, y_n), line, font=f_p, fill=(0,0,0), anchor="mm"); y_n += 22
            f_pv_fly = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 53)
            f_ps_fly = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 30)
            try: p_fmt = "{:,}".format(int(float(p['Precio desc'])))
            except: p_fmt = str(p['Precio desc'])
            if "EFERTON" in tipo:
                y_p_efe = yp + box_h - 105
                draw_efe_preciador(draw, cx_col2, y_p_efe, "S/", p_fmt, f_ps_fly, f_pv_fly, scale=preciador_scale + 0.4, padding_h=10)
                draw.text((cx_col2 + 8, y_p_efe + 50), str(p['SKU']), font=f_s_ind, fill=(0,0,0), anchor="mm")
            else:
                y_p_irr = yp + box_h - 88
                w_total_p = draw.textlength("S/", font=f_ps_fly) + 5 + draw.textlength(p_fmt, font=f_pv_fly)
                x_i = cx_col2 - (w_total_p // 2)
                draw.text((x_i, y_p_irr), "S/", font=f_ps_fly, fill="#FFA002", anchor="ls")
                draw.text((x_i + draw.textlength("S/", font=f_ps_fly) + 5, y_p_irr), p_fmt, font=f_pv_fly, fill="#FFA002", anchor="ls")
                draw.text((cx_col2 + 8, y_p_irr + 25), str(p['SKU']), font=f_s_ind, fill=(0,0,0), anchor="mm")
            line_c = "#00ACDE" if "EFERTON" in tipo else "#0A74DA"
            if i % 2 == 0 and (i + 1) < num_prod: draw_dotted_line(draw, (xp + 475, yp + 20), (xp + 475, yp + box_h - 20), line_c)
            if i < (num_prod - 2): draw_dotted_line(draw, (xp + 20, yp + box_h + 6), (xp + 450, yp + box_h + 6), line_c)
        l_m = 70 if "EFERTON" in tipo else 62
        draw_justified_text(draw, str(row['Legales']), ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", l_size + 2), 1835, l_m, 1080 - l_m, (255,255,255), line_spacing_offset=1, force_justify=True)
    else:
        pi = Image.open(BytesIO(requests.get(row['Foto del producto calado'], timeout=10).content)).convert("RGBA")
        if formato == "PPL":
            if "EFERTON" in tipo:
                # AJUSTE: Imagen reducida en 30px por lado (797-60, 820-60)
                pi.thumbnail((580, 580)); img.paste(pi, (190, 270), pi)
                draw.text((90, 930), row['Marca'], font=ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 30), fill=(255,255,255), anchor="ls")
                lines = textwrap.wrap(str(row['Nombre del producto']), width=25); ny = 890 if len(lines) > 1 else 900
                for line in lines[:3]: draw.text((500, ny), line, font=ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 25), fill=(255,255,255), anchor="mm"); ny += 28
                draw.text((500, ny + 5), str(row['SKU']), font=ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 22), fill=(255,255,255), anchor="mm")
                draw_efe_preciador(draw, 840, 910, "S/", precio_val, f_ps, f_pv, scale=1.0, tracking=-3)
                draw_justified_text(draw, str(row['Legales']), f_l, 998, 90, 990, (255,255,255), force_justify=True)
            else: 
                pi.thumbnail((682, 682)); img.paste(pi, (310, 287), pi)
                draw.text((91, 639), row['Marca'], font=ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 30), fill=(255,255,255), anchor="ls")
                lines = textwrap.wrap(row['Nombre del producto'], width=13); ny = 675
                for lp in lines[:4]: draw.text((91, ny), lp, font=ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 26), fill=(255,255,255), anchor="ls"); ny += 30
                y_s = ny + 10; draw.text((91, y_s), str(row['SKU']), font=ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 20), fill=(255,255,255), anchor="ls")
                py = max(830, y_s + 80); draw.text((91, py), "S/", font=ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 44), fill=(255,255,255), anchor="ls")
                draw.text((91 + draw.textlength("S/", font=ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 44)) + 10, py), precio_val, font=ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 80), fill=(255,255,255), anchor="ls")
                draw_justified_text(draw, str(row['Legales']), f_l, 998, 73, 1007, (255,255,255), force_justify=True)
        elif formato == "STORY":
            if "EFERTON" in tipo:
                pi.thumbnail((956, 956)); img.paste(pi, (72, 606), pi); ay = 1600
                # AJUSTE: Bloque de textos movidos 20px a la izquierda (239 -> 219)
                lx_story = 219
                draw.text((lx_story, ay), row['Marca'], font=f_m, fill=(255,255,255), anchor="ls")
                ny = ay + 55
                for lp in textwrap.wrap(row['Nombre del producto'], width=20)[:4]: draw.text((lx_story, ny), lp, font=f_p, fill=(255,255,255), anchor="ls"); ny += 45
                y_s = ny + 5; draw.text((lx_story, y_s), str(row['SKU']), font=f_s_ind, fill=(255,255,255), anchor="ls")
                draw_efe_preciador(draw, 780, 1650, "S/", precio_val, ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 64), ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 110), scale=1.1, padding_h=30)
                draw_justified_text(draw, str(row['Legales']), ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", l_size + 2), 1800, 70, 1010, (255,255,255), line_spacing_offset=1, force_justify=True)
            else:
                pi.thumbnail((935, 935)); img.paste(pi, (78, 580), pi); lx = 147
                draw.text((lx, 1563), row['Marca'], font=ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 46), fill=(255,255,255), anchor="ls")
                ny = 1615
                for lp in textwrap.wrap(row['Nombre del producto'], width=18)[:4]: draw.text((lx, ny), lp, font=ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 38), fill=(255,255,255), anchor="ls"); ny += 42
                y_s = ny + 10; draw.text((lx, y_s), str(row['SKU']), font=ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 29), fill=(255,255,255), anchor="ls")
                py_irr = 1658; draw.text((566, py_irr), "S/", font=ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 71), fill=(255,255,255), anchor="ls")
                draw.text((566 + draw.textlength("S/", font=ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 71)) + 15, py_irr), precio_val, font=ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 128), fill=(255,255,255), anchor="ls")
                draw_justified_text(draw, str(row['Legales']), ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", l_size + 2), 1800, 70, 1010, (255,255,255), line_spacing_offset=1, force_justify=True)
        elif formato == "DISPLAY":
            if "EFERTON" in tipo:
                # AJUSTE: Imagen reducida en 30px por lado (510-60)
                pi.thumbnail((450, 450)); img.paste(pi, (460, 25), pi); cx = 260
                draw.text((cx, 250), row['Marca'], font=ImageFont.truetype(f_m.path, f_m.size - 2), fill=(255,255,255), anchor="mm")
                ny = 290
                for line in textwrap.wrap(str(row['Nombre del producto']), width=20)[:2]: draw.text((cx, ny), line, font=f_p, fill=(255,255,255), anchor="mm"); ny += 25
                y_s = ny + 5; draw.text((cx, y_s), str(row['SKU']), font=f_s_ind, fill=(255,255,255), anchor="mm")
                draw_efe_preciador(draw, cx, max(380, y_s + 60), "S/", precio_val, f_ps, f_pv, scale=1.0, tracking=-3)
                draw_justified_text(draw, str(row['Legales']), f_l, 485, 40, 960, (255,255,255), force_justify=True)
            else:
                pi.thumbnail((485, 465)); img.paste(pi, (412, 24), pi); lx = 91
                draw.text((lx, 219), row['Marca'], font=f_m, fill=(255,255,255), anchor="ls")
                ny = 255
                for lp in textwrap.wrap(row['Nombre del producto'], width=20)[:4]: draw.text((lx, ny), lp, font=f_p, fill=(255,255,255), anchor="ls"); ny += 25
                y_s = ny + 5; draw.text((lx, y_s), str(row['SKU']), font=f_s_ind, fill=(255,255,255), anchor="ls")
                y_p = max(379, y_s + 70); draw.text((lx, y_p), "s/", font=ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 42), fill=(255,255,255), anchor="ls")
                draw.text((lx + draw.textlength("s/", font=ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 42)) + 10, y_p), precio_val, font=ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 76), fill=(255,255,255), anchor="ls")
                draw_justified_text(draw, str(row['Legales']), f_l, 490, 40, 960, (255,255,255), force_justify=True)

    # --- GUARDADO FINAL (SKU LIMPIO) ---
    sku_limpio = str(row['SKU'] or row['ID_Flyer']).replace("/", "-").replace("\\", "-")
    fname = f"{sku_limpio}_{formato}_{tienda}.jpg"
    img.save(f"output/{fname}", quality=95); return f"{RAW_URL}{fname}"

# --- INICIO DE EJECUCIÓN ---
data, res_sheet, viejos = get_sheets_data()
os.makedirs('output', exist_ok=True)
h_lima = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")
filas_para_google = []

# Ciclo 1: Productos Individuales
for idx, row in data.iterrows():
    f_v = str(row['Formato']).upper().strip()
    if f_v in ["FLYER", "", "0"]: continue 
    tienda = str(row.get('Tienda', 'LC')).strip().upper()
    sku_val = str(row['SKU']).replace("/", "-").replace("\\", "-")
    llave = f"{sku_val}_{f_v}_{tienda}_EFE".upper()
    if llave not in viejos:
        print(f"🎨 Generando: {llave}")
        url = generar_diseno(row)
        if url: filas_para_google.append([h_lima, llave, tienda, row['Tipo de diseño'], f_v, "EFE", url])

# Ciclo 2: Flyers
fly_g = data[data['Formato'].astype(str).str.upper().str.strip() == "FLYER"]
for id_f, group in fly_g.groupby('ID_Flyer'):
    if str(id_f) in ["0", "0.0", ""]: continue
    id_limpio = str(id_f).replace("/", "-").replace("\\", "-")
    llave = f"{id_limpio}_FLYER_EFE".upper()
    if llave not in viejos:
        print(f"🎨 Generando Flyer: {llave}")
        url = generar_diseno(group)
        if url: filas_para_google.append([h_lima, llave, "EFE", group.iloc[0]['Tipo de diseño'], "FLYER", "EFE", url])

# --- ESCRITURA FINAL ---
if filas_para_google:
    res_sheet.append_rows(filas_para_google)
    print(f"✅ Éxito: Se registraron {len(filas_para_google)} piezas nuevas.")
else:
    print("No se generaron piezas nuevas. Creando placeholder.")
    with open("output/placeholder.txt", "w") as f: f.write(f"Sin cambios: {h_lima}")