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
# Usuario de GitHub donde se alojan los recursos
USER_GH = "analyticsdatajg2025-cmd"
# Nombre del repositorio
REPO_GH = "GITHUB_CATALOGOS_CONECTA"
# URL base para acceder a las imágenes generadas públicamente
RAW_URL = f"https://raw.githubusercontent.com/{USER_GH}/{REPO_GH}/main/output/"

def draw_justified_text(draw, text, font, y_start, x_start, x_end, fill, line_spacing_offset=0, force_justify=False):
    # 1. Preparación del prefijo y fuentes
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
    
    # 2. LÓGICA DE SALTO DE LÍNEA POR PÍXELES (Automática)
    lines = []
    current_line = []
    current_width = 0
    space_w = draw.textlength(" ", font=font)

    for word in words:
        # Verificamos si es una de las palabras en negrita para medirla bien
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

    # 3. DIBUJO Y JUSTIFICACIÓN
    for i, line_words in enumerate(lines):
        if not line_words: continue

        is_last_line = (i == len(lines) - 1)
        # Medimos el ancho real de la línea para el umbral de vacío
        line_pixels = sum(draw.textlength(w, font=font_bold if (i==0 and j<=1) else font) for j, w in enumerate(line_words))
        too_empty = line_pixels < (container_width * 0.7)

        if is_last_line or too_empty or not force_justify:
            # ALINEACIÓN IZQUIERDA
            x_cursor = x_start
            for j, word in enumerate(line_words):
                current_font = font_bold if (i == 0 and j <= 1) else font
                draw.text((x_cursor, y_start), word, font=current_font, fill=fill)
                x_cursor += draw.textlength(word, font=current_font) + space_w
        else:
            # JUSTIFICACIÓN MATEMÁTICA
            total_words_w = sum(draw.textlength(w, font=font_bold if (i == 0 and j <= 1) else font) for j, w in enumerate(line_words))
            # Calculamos el espacio exacto para que toque ambos bordes (x_start y x_end)
            dynamic_space = (container_width - total_words_w) / (len(line_words) - 1)
            
            x_cursor = x_start
            for j, word in enumerate(line_words):
                current_font = font_bold if (i == 0 and j <= 1) else font
                draw.text((x_cursor, y_start), word, font=current_font, fill=fill)
                x_cursor += draw.textlength(word, font=current_font) + dynamic_space
        
        y_start += line_height

# Función para dibujar líneas punteadas divisorias
def draw_dotted_line(draw, start, end, fill, width=2, gap=8):
    curr_x, curr_y = start
    dest_x, dest_y = end
    dx, dy = dest_x - curr_x, dest_y - curr_y
    dist = (dx**2 + dy**2)**0.5 # Pitágoras para saber la distancia total
    if dist == 0: return
    sx, sy = dx/dist, dy/dist
    # Dibuja segmentos de línea saltando espacios (gap * 2)
    for i in range(0, int(dist), gap * 2):
        s = (curr_x + sx * i, curr_y + sy * i)
        e = (curr_x + sx * (i + gap), curr_y + sy * (i + gap))
        draw.line([s, e], fill=fill, width=width)

def draw_efe_preciador(draw, x_center, y_center, text_s, text_price, f_ps, f_pv, scale=1.0, tracking=-2, padding_h=20):
    num_w = 0
    for char in text_price:
        num_w += draw.textlength(char, font=f_pv) + tracking
    num_w -= tracking 
    sym_w = draw.textlength(text_s, font=f_ps)
    
    gap = 8 * scale 
    full_w = sym_w + gap + num_w
    font_size = f_pv.size
    
    # Mantenemos el 1.2 que redujo la altura vertical
    h = int(font_size * 1.2 * scale) 

    # Ahora el padding horizontal es variable
    p_h = padding_h * scale
    
    draw.rounded_rectangle([x_center - full_w//2 - p_h, y_center - h//2, 
                             x_center + full_w//2 + p_h, y_center + h//2], 
                            radius=15, fill="#FFA002")
    
    tx = x_center - full_w//2
    draw.text((tx, y_center), text_s, font=f_ps, fill=(255,255,255), anchor="lm")
    
    curr_x = tx + sym_w + gap
    for char in text_price:
        draw.text((curr_x, y_center), char, font=f_pv, fill=(255,255,255), anchor="lm")
        curr_x += draw.textlength(char, font=f_pv) + tracking

# Conexión con la API de Google Sheets y obtención de datos
def get_sheets_data():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # Carga credenciales desde variables de entorno
    creds_info = json.loads(os.environ.get('GOOGLE_CREDENTIALS'))
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    client = gspread.authorize(creds)
    # Abre el documento por su ID
    sheet = client.open_by_key("1PmvCyC3d0VvvZSdvWM73NYusrYevVYtRzVs2gbxjw1M")
    # Lee los datos de la hoja principal
    data = pd.DataFrame(sheet.worksheet("Hoja 1").get_all_records())
    data.columns = [c.strip() for c in data.columns]
    # Revisa qué diseños ya fueron procesados para no repetirlos
    res_sheet = sheet.worksheet("Resultados")
    v_act = res_sheet.get_all_values()
    viejos = {r[1].strip().upper() for r in v_act[1:] if len(r) > 1}
    return data, res_sheet, viejos

# Lógica principal de dibujo según el formato
def generar_diseno(data_input, color_version="AMARILLO"):
    # Detecta si es un Flyer (varios productos) o un diseño individual
    is_flyer = isinstance(data_input, pd.DataFrame)
    row = data_input.iloc[0] if is_flyer else data_input
    tienda = str(row.get('Tienda', 'LC')).strip().upper()
    tipo = str(row['Tipo de diseño']).strip().upper()
    formato = str(row['Formato']).upper().strip()
    path_fonts, path_fondos = f"TIPOGRAFIA/{tienda}", f"FONDOS/{tienda}/{tipo}"

    # --- DEFINICIÓN DE FONDO ---
    # Busca el archivo de fondo que coincida con la tienda, tipo y formato
    f_names = [f"{tienda} - {tipo} - {formato}", f"{tienda} - REPOWER {tipo} - {formato}"]
    full_p = next((os.path.join(path_fondos, f"{v}{e}") for v in f_names for e in [".jpg", ".png", ".JPG"] if os.path.exists(os.path.join(path_fondos, f"{v}{e}"))), None)
    
    if not full_p: return None
    img = Image.open(full_p).convert("RGB")
    draw = ImageDraw.Draw(img)

    # --- CONFIGURACIÓN DE TAMAÑOS DE FUENTE ---
    try:
        # Valores base: p_size (Precio), s_size (Símbolo), l_size (Legales)
        p_size = 90; s_size = 35; l_size = 10
        if formato == "DISPLAY": 
            p_size = 60; s_size = 30; l_size = 8
        elif formato == "STORY": 
            p_size = 100; s_size = 40
        elif formato == "FLYER":
            p_size = 50; s_size = 25
        
        # Carga de archivos .ttf específicos
        f_m = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 44 if formato == "STORY" else 32)
        f_p = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 30 if formato == "STORY" else 20)
        f_pv = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", p_size) # Precio grande
        f_ps = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", s_size) # S/ del precio
        f_s_ind = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 18 if formato == "STORY" else 15) # SKU
        f_l = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", l_size) # Bloque legal
        f_f = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 26) # Texto de fecha en Flyer
    except: f_m = f_p = f_pv = f_ps = f_s_ind = f_l = f_f = ImageFont.load_default()

# --- LÓGICA ESPECÍFICA PARA FORMATO: FLYER (Centrado Dinámico y Ajustes de Diseño) ---
    if formato == "FLYER":
        f_txt = str(row['Fecha_disponibilidad_flyer']).upper()
    
        # Bloque de fecha con contenedor naranja
        rect_x, rect_y = (163 if "IRRESISTIBLE" in tipo else 190), 244
        f_f_semibold = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 23)
        w_f, h_f = draw.textlength(f_txt, font=f_f_semibold), 40
        draw.rounded_rectangle([rect_x, rect_y, rect_x + w_f + 40, rect_y + h_f], radius=10, fill="#FFA002")
        draw.text((rect_x + (w_f + 40)//2, rect_y + h_f//2), f_txt, font=f_f_semibold, fill=(255,255,255), anchor="mm")
        
        num_prod = len(data_input)
        y_limit_top = 350
        y_limit_bottom = 1757
        available_h = y_limit_bottom - y_limit_top
        
        # --- ESTA PARTE DEBE ESTAR INDENTADA DENTRO DEL IF FLYER ---
        if num_prod > 6:
            rows = 4
            box_h = 340
            img_size_w, img_size_h = 350, 220 
            preciador_scale = 0.45
        else:
            rows = 3
            box_h = 430 
            img_size_w, img_size_h = 434, 292
            preciador_scale = 0.55

        # CÁLCULO DE CENTRADO VERTICAL
        total_content_h = (rows * box_h) + ((rows - 1) * 12)
        y_centering_offset = (available_h - total_content_h) // 2
        current_y_top = y_limit_top + y_centering_offset

        for i, (idx, p) in enumerate(data_input.iterrows()):
            if i >= 8: break
            
            xp = 65 + (i % 2) * 495
            yp = current_y_top + (i // 2) * (box_h + 12)
            
            # Pegado de imagen centrada
            try:
                url_foto = p.get('Foto del producto calado') or p.get('Foto')
                if url_foto:
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    pi_res = requests.get(url_foto, headers=headers, timeout=10)
                    pi_fly = Image.open(BytesIO(pi_res.content)).convert("RGBA")
                    pi_fly.thumbnail((img_size_w, img_size_h))
                    ix = int(xp + 240 - pi_fly.width // 2)
                    iy = int(yp + 20) 
                    img.paste(pi_fly, (ix, iy), pi_fly)
            except: pass

            cx_col1 = xp + 125
            cx_col2 = xp + 345
            
            # 1. Marca y Nombre (Máximo 2 filas)
            f_m_flyer = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 28)
            draw.text((cx_col1, yp + box_h - 115), p['Marca'], font=f_m_flyer, fill=(0,0,0), anchor="mm")
            
            lineas_nombre = textwrap.wrap(str(p['Nombre del producto']), width=18)
            y_nombre = yp + box_h - 85
            for line in lineas_nombre[:2]: 
                draw.text((cx_col1, y_nombre), line, font=f_p, fill=(0,0,0), anchor="mm")
                y_nombre += 22
            
            # 2. Precio y SKU (A ras y solo valor)
            f_pv_fly = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 53)
            f_ps_fly = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 30)
            y_precio = yp + box_h - 85 
            
            if "EFERTON" in tipo:
                draw_efe_preciador(draw, cx_col2, y_precio, "S/", str(p['Precio desc']), f_ps_fly, f_pv_fly, scale=preciador_scale, padding_h=25)
                draw.text((cx_col2, y_precio + 45), str(p['SKU']), font=f_s_ind, fill=(0,0,0), anchor="mm")
            else:
                # --- PRECIO IRRESISTIBLE ---
                # 1. Mantenemos tu lógica de dibujo de precio tal cual (alineado a la izquierda)
                w_s = draw.textlength("S/", font=f_ps_fly)
                w_num = draw.textlength(str(p['Precio desc']), font=f_pv_fly)
                gap = 5
                
                # Calculamos dónde empieza el bloque para que el conjunto esté centrado en la columna
                w_total_p = w_s + gap + w_num
                x_ini_p = cx_col2 - (w_total_p // 2)
                
                # Dibujo del precio (esto no cambia su posición actual)
                draw.text((x_ini_p, y_precio), "S/", font=f_ps_fly, fill="#FFA002", anchor="ls")
                draw.text((x_ini_p + w_s + gap, y_precio), str(p['Precio desc']), font=f_pv_fly, fill="#FFA002", anchor="ls")
                
                # 2. AJUSTE DEL SKU: Para que esté justo debajo del centro del precio
                # Usamos cx_col2 con anchor "mm" para que se alinee con el eje central del bloque de arriba
                draw.text((cx_col2, y_precio + 35), str(p['SKU']), font=f_s_ind, fill=(0,0,0), anchor="mm")
            
            # Divisores
            line_c = "#00ACDE" if "EFERTON" in tipo else "#0A74DA"
            if i % 2 == 0 and (i + 1) < num_prod: 
                draw_dotted_line(draw, (xp + 475, yp + 20), (xp + 475, yp + box_h - 20), line_c)
            if i < (num_prod - 2):
                draw_dotted_line(draw, (xp + 20, yp + box_h + 6), (xp + 450, yp + box_h + 6), line_c)

        # Legales Flyer
        l_margin = 70 if "EFERTON" in tipo else 62
        f_l_flyer = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", l_size + 2)
        draw_justified_text(draw, str(row['Legales']), f_l_flyer, 1835, l_margin, 1080 - l_margin, (255,255,255), line_spacing_offset=1, force_justify=True)

    # --- LÓGICA PARA OTROS FORMATOS (PPL, STORY, DISPLAY) ---
    else:
        headers = {'User-Agent': 'Mozilla/5.0'}
        pi_res = requests.get(row['Foto del producto calado'], headers=headers, timeout=10)
        pi = Image.open(BytesIO(pi_res.content)).convert("RGBA")
        
        # --- FORMATO: PPL (Post / Pieza Principal) ---
        if formato == "PPL":
            if "EFERTON" in tipo:
                # 1. IMAGEN: X=126, Y=269, Tamaño 747x270
                pi.thumbnail((747, 770))
                img.paste(pi, (126, 269), pi)
                
                # --- COLUMNAS IMAGINARIAS (Y base ajustada con los +70, +52, +80) ---
                
                # COLUMNA 1: MARCA (Comienza en X=90, Y=900)
                f_m_efe = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 30) # -2pts de los 32 originales
                draw.text((90, 930), row['Marca'], font=f_m_efe, fill=(255,255,255), anchor="ls")
                
                # COLUMNA 2: NOMBRE Y SKU (Centro del banner X=500, pero bajados)
                # Nombre: 830 + 15 (original) + 52 (pedido) = 897 
                f_p_efe = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 25)
                draw.text((500, 900), row['Nombre del producto'][:25], font=f_p_efe, fill=(255,255,255), anchor="mm")
                
                # SKU: 830 + 55 (original) + 52 (pedido) = 937
                f_s_efe = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 22)
                draw.text((500, 935), str(row['SKU']), font=f_s_efe, fill=(255,255,255), anchor="mm")
                
                # COLUMNA 3: PRECIO (X=840, Y=910)
                # 830 + 80 (pedido) = 910. El "S/" se alinea solo dentro de la función del preciador.
                draw_efe_preciador(draw, 840, 910, "S/", str(row['Precio desc']), f_ps, f_pv, scale=1.0, tracking=-3)
                
                # LEGALES: Y=998 (980+18), Margen 90px (X_ini=90, X_fin=910)
                # force_justify=False para que no se vea tan separado
                draw_justified_text(draw, str(row['Legales']), f_l, 998, 90, 990, (255,255,255), line_spacing_offset=0, force_justify=True)
                
            else: 
                # --- PPL PRECIO IRRESISTIBLE ---
                # Imagen: 622px, X=290, Y=287
                pi.thumbnail((622, 622))
                img.paste(pi, (290, 287), pi)
                
                lx = 91 # Margen izquierdo para textos
                
                # Marca: Y=639, Tamaño 30pts
                f_m_irr = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 30)
                draw.text((lx, 639), row['Marca'], font=f_m_irr, fill=(255,255,255), anchor="ls")
                
                # Nombre del producto: Tamaño 26pts, X=91, Máximo hasta X=290
                f_p_irr = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 26)
                # Wrap ajustado para no pasar del ancho solicitado (aprox 15-18 caracteres)
                lines_prod = textwrap.wrap(row['Nombre del producto'], width=15)
                ny = 675 
                for lp in lines_prod[:2]:
                    draw.text((lx, ny), lp, font=f_p_irr, fill=(255,255,255), anchor="ls")
                    ny += 30
                
                # SKU: Tamaño 20pts
                f_s_irr = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 20)
                draw.text((lx, ny + 10), str(row['SKU']), font=f_s_irr, fill=(255,255,255), anchor="ls")
                
                # Precio: S/ 44pts, Precio 80pts (ExtraBold)
                f_pv80 = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 80)
                f_ps44 = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 44)
                
                # Alineación al ras (py=830) para que el símbolo y el precio asienten en la misma base
                py = 830 
                w_s = draw.textlength("S/", font=f_ps44)
                
                # Dibujamos S/ y Precio usando la misma coordenada 'py' y anchor 'ls'
                draw.text((lx, py), "S/", font=f_ps44, fill=(255,255,255), anchor="ls")
                draw.text((lx + w_s + 10, py), str(row['Precio desc']), font=f_pv80, fill=(255,255,255), anchor="ls")
                
                # Legales Irresistible: Margen 73px (X_ini=73, X_fin=927), Y=937
                draw_justified_text(draw, str(row['Legales']), f_l, 998, 73, 1007, (255,255,255), line_spacing_offset=0, force_justify=True)

# --- FORMATO: STORY (9:16 - Ajustes Eferton e Irresistible) ---
        elif formato == "STORY":
            # 1. LÓGICA PARA EFERTON
            if "EFERTON" in tipo:
                pi.thumbnail((936, 936))
                img.paste(pi, (72, 606), pi)
                
                ay = 1600 
                # Marca
                draw.text((239, ay), row['Marca'], font=f_m, fill=(255,255,255), anchor="ls")
                
                # Nombre del producto: Dinámico hasta 2 líneas
                lines_prod = textwrap.wrap(row['Nombre del producto'], width=25)
                ny = ay + 55
                for lp in lines_prod[:2]:
                    draw.text((239, ny), lp, font=f_p, fill=(255,255,255), anchor="ls")
                    ny += 45 # Salto entre líneas del nombre
                
                # SKU dinámico: Se posiciona debajo de la última línea del nombre
                y_sku = ny + 5
                draw.text((239, y_sku), str(row['SKU']), font=f_s_ind, fill=(255,255,255), anchor="ls")
                
                # PRECIO EFERTON A RAS
                f_pv_efe = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 110)
                f_ps_efe = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 64)
                
                py_efe = 1655 # Base común para ambos
                draw.text((613, py_efe), "S/", font=f_ps_efe, fill=(255,255,255), anchor="ls")
                w_s = draw.textlength("S/", font=f_ps_efe)
                draw.text((613 + w_s + 12, py_efe), str(row['Precio desc']), font=f_pv_efe, fill=(255,255,255), anchor="ls")
                
                # Legales Eferton
                f_l_story = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", l_size + 2)
                draw_justified_text(draw, str(row['Legales']), f_l_story, 1800, 70, 1010, (255,255,255), line_spacing_offset=1, force_justify=True)

            # 2. LÓGICA PARA IRRESISTIBLE
            else:
                pi.thumbnail((905, 905))
                img.paste(pi, (76, 596), pi)
                
                lx = 147 
                # Marca
                f_m_irr = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 46)
                draw.text((lx, 1563), row['Marca'], font=f_m_irr, fill=(255,255,255), anchor="ls")
                
                # Nombre Producto: Dinámico 2 líneas
                f_p_irr = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 38)
                lines_prod = textwrap.wrap(row['Nombre del producto'], width=18)
                ny = 1615
                for lp in lines_prod[:2]:
                    draw.text((lx, ny), lp, font=f_p_irr, fill=(255,255,255), anchor="ls")
                    ny += 42 
                
                # SKU dinámico
                y_sku = ny + 10
                f_s_irr = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 29)
                draw.text((lx, y_sku), str(row['SKU']), font=f_s_irr, fill=(255,255,255), anchor="ls")
                
                # PRECIO IRRESISTIBLE A RAS
                f_pv_irr = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 128)
                f_ps_irr = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 71)
                
                py_irr = 1658 # Base común para ambos
                draw.text((566, py_irr), "S/", font=f_ps_irr, fill=(255,255,255), anchor="ls")
                w_s_irr = draw.textlength("S/", font=f_ps_irr)
                draw.text((566 + w_s_irr + 15, py_irr), str(row['Precio desc']), font=f_pv_irr, fill=(255,255,255), anchor="ls")
                
                # Legales Irresistible
                f_l_story = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", l_size + 2)
                draw_justified_text(draw, str(row['Legales']), f_l_story, 1800, 70, 1010, (255,255,255), line_spacing_offset=1, force_justify=True)

# --- FORMATO: DISPLAY (Ajustes Eferton e Irresistible) ---
        elif formato == "DISPLAY":
            # 1. LÓGICA PARA EFERTON
            if "EFERTON" in tipo:
                # Imagen: 463px, Y=25, X=440
                pi.thumbnail((463, 463))
                img.paste(pi, (440, 25), pi)
                
                cx = 260 # Centro para Eferton
                # Usamos el f_m definido arriba pero le restamos 2 al tamaño
                f_m_small = ImageFont.truetype(f_m.path, f_m.size - 2)
                draw.text((cx, 250), row['Marca'], font=f_m_small, fill=(255,255,255), anchor="mm")
                
                # Nombre Producto
                draw.text((cx, 290), row['Nombre del producto'][:25], font=f_p, fill=(255,255,255), anchor="mm")
                
                # SKU: Subir 7px (Y: 320 - 7 = 313)
                draw.text((cx, 313), str(row['SKU']), font=f_s_ind, fill=(255,255,255), anchor="mm")
                
                # Precio: 60pts, S/: 30pts (f_pv y f_ps ya tienen estos tamaños en el config)
                draw_efe_preciador(draw, cx, 380, "S/", str(row['Precio desc']), f_ps, f_pv, scale=1.0, tracking=-3)
                
                # Legales Eferton: X inicial 40, X final 486 (como ya bajamos la posicion de legales, ahora ocupa todo el ancho pero margen 40px ambos lados)
                draw_justified_text(draw, str(row['Legales']), f_l, 490, 40, 960, (255,255,255), line_spacing_offset=0, force_justify=True)

            # 2. LÓGICA PARA IRRESISTIBLE (DISPLAY)
            else:
                # Imagen: 465px, Y=24, X=412
                pi.thumbnail((465, 465))
                img.paste(pi, (412, 24), pi)
                
                lx = 91 # Margen izquierdo
                
                # Marca: Y=219
                draw.text((lx, 219), row['Marca'], font=f_m, fill=(255,255,255), anchor="ls")
                
                # Nombre del producto: 2 filas máximo, interlineado de 25px
                lines_prod = textwrap.wrap(row['Nombre del producto'], width=20)
                ny = 255 
                for lp in lines_prod[:2]:
                    draw.text((lx, ny), lp, font=f_p, fill=(255,255,255), anchor="ls")
                    ny += 25 # Mantenemos tus 25px originales
                
                # SKU: Justo debajo del nombre
                y_sku = ny + 5
                draw.text((lx, y_sku), str(row['SKU']), font=f_s_ind, fill=(255,255,255), anchor="ls")
                
                # PRECIO DINÁMICO: Se posiciona relativo al SKU para evitar que se choquen
                # Si el SKU baja por la segunda línea del nombre, el precio baja con él
                y_precio = max(379, y_sku + 70)

                f_pv_irr = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 76)
                f_ps_irr = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 42)
                
                # Símbolo s/ y Precio: Comparten y_precio para alinearse al ras (base común)
                w_s_irr = draw.textlength("s/", font=f_ps_irr)
                draw.text((lx, y_precio), "s/", font=f_ps_irr, fill=(255,255,255), anchor="ls")
                
                # Precio: lx + ancho del s/ + 10px de aire
                draw.text((lx + w_s_irr + 10, y_precio), str(row['Precio desc']), font=f_pv_irr, fill=(255,255,255), anchor="ls")
                
                # Legales: Los mantenemos en el fondo
                draw_justified_text(draw, str(row['Legales']), f_l, 490, 40, 960, (255,255,255), line_spacing_offset=0, force_justify=True)

    # --- GUARDADO FINAL ---
    # Nombra el archivo con SKU/ID, formato y tienda
    fname = f"{row['SKU'] or row['ID_Flyer']}_{formato}_{tienda}.jpg"
    img.save(f"output/{fname}", quality=95); return f"{RAW_URL}{fname}"

# --- INICIO DE EJECUCIÓN ---
data, res_sheet, viejos = get_sheets_data(); os.makedirs('output', exist_ok=True)
# Obtención de hora actual (Lima UTC-5)
h_lima = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")

# Ciclo 1: Procesa todos los formatos que NO son FLYER
for idx, row in data.iterrows():
    f_v = str(row['Formato']).upper().strip()
    if f_v in ["FLYER", "", "0"]: continue # Salta Flyers para el segundo ciclo
    tienda = str(row.get('Tienda', 'LC')).strip().upper()
    llave = f"{row['SKU']}_{f_v}_{tienda}_EFE".upper()
    # Solo genera si la "llave" no está en la lista de procesados
    if llave not in viejos:
        url = generar_diseno(row)
        if url: res_sheet.append_row([h_lima, llave, tienda, row['Tipo de diseño'], f_v, "EFE", url])

# Ciclo 2: Procesa específicamente los FLYERS (agrupando por ID_Flyer)
fly_g = data[data['Formato'].astype(str).str.upper().str.strip() == "FLYER"]
for id_f, group in fly_g.groupby('ID_Flyer'):
    if str(id_f) in ["0", "0.0", ""]: continue
    llave = f"{id_f}_FLYER_EFE".upper()
    if llave not in viejos:
        url = generar_diseno(group) # Aquí pasa el grupo de productos al generador
        if url: res_sheet.append_row([h_lima, llave, "EFE", group.iloc[0]['Tipo de diseño'], "FLYER", "EFE", url])
