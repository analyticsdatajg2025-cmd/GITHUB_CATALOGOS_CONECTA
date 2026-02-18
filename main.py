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

        total_content_h = (rows * box_h) + ((rows - 1) * 12)
        y_centering_offset = (available_h - total_content_h) // 2
        current_y_top = y_limit_top + y_centering_offset

        for i, (idx, p) in enumerate(data_input.iterrows()):
            if i >= 8: break
            
            xp = 65 + (i % 2) * 495
            yp = current_y_top + (i // 2) * (box_h + 12)
            
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
            
            # 1. Marca y Nombre
            f_m_flyer = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 28)
            draw.text((cx_col1, yp + box_h - 115), p['Marca'], font=f_m_flyer, fill=(0,0,0), anchor="mm")
            
            lineas_nombre = textwrap.wrap(str(p['Nombre del producto']), width=18)
            y_nombre = yp + box_h - 85
            for line in lineas_nombre[:4]: 
                draw.text((cx_col1, y_nombre), line, font=f_p, fill=(0,0,0), anchor="mm")
                y_nombre += 22
            
            # 2. Precio y SKU
            f_pv_fly = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 53)
            f_ps_fly = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 30)
            
            if "EFERTON" in tipo:
                # Bajamos y_precio de -115 a -105 para acercarlo al SKU
                y_precio_efe = yp + box_h - 105
                # Aumentamos scale a + 0.15 para que el preciador se vea más robusto
                draw_efe_preciador(draw, cx_col2, y_precio_efe, "S/", str(p['Precio desc']), f_ps_fly, f_pv_fly, scale=preciador_scale + 0.4, padding_h=10)
                # SKU movido +8px a la derecha para centrarlo bajo el bloque de precio
                draw.text((cx_col2 + 8, y_precio_efe + 50), str(p['SKU']), font=f_s_ind, fill=(0,0,0), anchor="mm")
            else:
                # --- PRECIO IRRESISTIBLE ---
                # Bajamos y_precio de -115 a -100 para que no esté tan separado del SKU
                y_precio_irr = yp + box_h - 88
                w_s = draw.textlength("S/", font=f_ps_fly)
                w_num = draw.textlength(str(p['Precio desc']), font=f_pv_fly)
                gap = 5
                w_total_p = w_s + gap + w_num
                x_ini_p = cx_col2 - (w_total_p // 2)
                
                draw.text((x_ini_p, y_precio_irr), "S/", font=f_ps_fly, fill="#FFA002", anchor="ls")
                draw.text((x_ini_p + w_s + gap, y_precio_irr), str(p['Precio desc']), font=f_pv_fly, fill="#FFA002", anchor="ls")
                
                # SKU movido +8px a la derecha y acercado al precio (+35 en lugar de +45)
                draw.text((cx_col2 + 8, y_precio_irr + 25), str(p['SKU']), font=f_s_ind, fill=(0,0,0), anchor="mm") 

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
                # 1. IMAGEN
                pi.thumbnail((797, 820))
                img.paste(pi, (126, 175), pi)
                
                # COLUMNA 1: MARCA
                f_m_efe = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 30)
                draw.text((90, 930), row['Marca'], font=f_m_efe, fill=(255,255,255), anchor="ls")
                
                # COLUMNA 2: NOMBRE Y SKU (Dinámico)
                f_p_efe = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 25)
                f_s_efe = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 22)
                
                # Procesamos el nombre (ancho de 30 para que use bien el espacio central)
                lineas_nombre = textwrap.wrap(str(row['Nombre del producto']), width=30)
                
                # El nombre empezaba originalmente en 900 (anchor mm)
                # Si hay más filas, subimos el inicio un poco para que no choque con legales
                ny = 890 if len(lineas_nombre) > 1 else 900
                
                for line in lineas_nombre[:3]: # Permitimos hasta 3 filas
                    draw.text((500, ny), line, font=f_p_efe, fill=(255,255,255), anchor="mm")
                    ny += 28 # Espaciado entre líneas del nombre
                
                # El SKU se posiciona relativo al final del nombre
                # Antes estaba fijo en 935, ahora es dinámico
                y_sku = ny + 5
                draw.text((500, y_sku), str(row['SKU']), font=f_s_efe, fill=(255,255,255), anchor="mm")
                
                # COLUMNA 3: PRECIO (Fijo para mantener alineación con Marca)
                draw_efe_preciador(draw, 840, 910, "S/", str(row['Precio desc']), f_ps, f_pv, scale=1.0, tracking=-3)
                
                # LEGALES: Fijos en 998
                draw_justified_text(draw, str(row['Legales']), f_l, 998, 90, 990, (255,255,255), line_spacing_offset=0, force_justify=True)
            else: 
                # --- PPL PRECIO IRRESISTIBLE ---
                # Imagen
                pi.thumbnail((682, 682))
                img.paste(pi, (310, 287), pi)
                
                lx = 91 # Margen izquierdo para textos
                
                # Marca: Fija en Y=639
                f_m_irr = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 30)
                draw.text((lx, 639), row['Marca'], font=f_m_irr, fill=(255,255,255), anchor="ls")
                
                # Nombre del producto: Dinámico hasta 4 filas
                f_p_irr = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 26)
                lines_prod = textwrap.wrap(row['Nombre del producto'], width=13)
                
                ny = 675 
                for lp in lines_prod[:4]:
                    draw.text((lx, ny), lp, font=f_p_irr, fill=(255,255,255), anchor="ls")
                    ny += 30 # Salto de línea
                
                # SKU: Se posiciona relativo al final del nombre
                f_s_irr = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 20)
                y_sku = ny + 10
                draw.text((lx, y_sku), str(row['SKU']), font=f_s_irr, fill=(255,255,255), anchor="ls")
                
                # PRECIO DINÁMICO: S/ 44pts, Precio 80pts
                f_pv80 = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 80)
                f_ps44 = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 44)
                
                # LÓGICA DE SEGURIDAD: 
                # El precio base es 830, pero si el SKU baja mucho, el precio baja con él
                # (dejamos 80px de margen entre el SKU y la base del precio)
                py = max(830, y_sku + 80) 
                
                w_s = draw.textlength("S/", font=f_ps44)
                draw.text((lx, py), "S/", font=f_ps44, fill=(255,255,255), anchor="ls")
                draw.text((lx + w_s + 10, py), str(row['Precio desc']), font=f_pv80, fill=(255,255,255), anchor="ls")
                
                # Legales Irresistible: Fijos en el fondo
                draw_justified_text(draw, str(row['Legales']), f_l, 998, 73, 1007, (255,255,255), line_spacing_offset=0, force_justify=True)
       
        # --- FORMATO: STORY (9:16 - Ajustes Eferton e Irresistible) ---
        elif formato == "STORY":
            # 1. LÓGICA PARA EFERTON
            if "EFERTON" in tipo:
                pi.thumbnail((956, 956))
                img.paste(pi, (72, 606), pi)
                
                ay = 1600 
                # Marca
                draw.text((239, ay), row['Marca'], font=f_m, fill=(255,255,255), anchor="ls")
                
                # Nombre del producto: Dinámico hasta 2 líneas
                lines_prod = textwrap.wrap(row['Nombre del producto'], width=20)
                ny = ay + 55
                for lp in lines_prod[:4]:
                    draw.text((239, ny), lp, font=f_p, fill=(255,255,255), anchor="ls")
                    ny += 45 
                
                # SKU dinámico
                y_sku = ny + 5
                draw.text((239, y_sku), str(row['SKU']), font=f_s_ind, fill=(255,255,255), anchor="ls")
                
                # --- PRECIO EFERTON CON PRECIADOR NARANJA ---
                f_pv_efe = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 110)
                f_ps_efe = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 64)

                # Usamos X=780 para centrar el bloque naranja en el espacio derecho
                px_story = 780
                py_story = 1650

                # Solo llamamos a la función (eliminamos el dibujo de texto manual que tenías después)
                draw_efe_preciador(draw, px_story, py_story, "S/", str(row['Precio desc']), f_ps_efe, f_pv_efe, scale=1.1, padding_h=30)
                
                # Legales Eferton
                f_l_story = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", l_size + 2)
                draw_justified_text(draw, str(row['Legales']), f_l_story, 1800, 70, 1010, (255,255,255), line_spacing_offset=1, force_justify=True)

            # 2. LÓGICA PARA IRRESISTIBLE
            else:
                pi.thumbnail((935, 935))
                img.paste(pi, (78, 580), pi)
                
                lx = 147 
                # Marca
                f_m_irr = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 46)
                draw.text((lx, 1563), row['Marca'], font=f_m_irr, fill=(255,255,255), anchor="ls")
                
                # Nombre Producto: Dinámico 2 líneas
                f_p_irr = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 38)
                lines_prod = textwrap.wrap(row['Nombre del producto'], width=18)
                ny = 1615
                for lp in lines_prod[:4]:
                    draw.text((lx, ny), lp, font=f_p_irr, fill=(255,255,255), anchor="ls")
                    ny += 42 
                
                # SKU dinámico
                y_sku = ny + 10
                f_s_irr = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 29)
                draw.text((lx, y_sku), str(row['SKU']), font=f_s_irr, fill=(255,255,255), anchor="ls")
                
                # PRECIO IRRESISTIBLE A RAS (Este se mantiene como texto blanco)
                f_pv_irr = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 128)
                f_ps_irr = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 71)
                
                py_irr = 1658 
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
                # Imagen: 510px, Y=25, X=430
                pi.thumbnail((510, 510))
                img.paste(pi, (430, 25), pi)
                
                cx = 260 # Centro para Eferton
                f_m_small = ImageFont.truetype(f_m.path, f_m.size - 2)
                draw.text((cx, 250), row['Marca'], font=f_m_small, fill=(255,255,255), anchor="mm")
                
                # --- NOMBRE DEL PRODUCTO (Máximo 2 filas, 20 caracteres) ---
                lineas_nombre = textwrap.wrap(str(row['Nombre del producto']), width=20)
                
                ny = 290  # Inicio del nombre
                for line in lineas_nombre[:2]: # Limitado a 2 filas según tu pedido
                    draw.text((cx, ny), line, font=f_p, fill=(255,255,255), anchor="mm")
                    ny += 25 # Interlineado de 25px
                    
                # --- SKU (Posición dinámica) ---
                # Si hay 1 fila, ny será 315. Si hay 2, será 340.
                y_sku = ny + 5
                draw.text((cx, y_sku), str(row['SKU']), font=f_s_ind, fill=(255,255,255), anchor="mm")
                
                # --- PRECIO (Posición base 380, baja solo si es necesario) ---
                # Si el nombre es largo, el precio bajará ligeramente de 380 para no chocar
                y_precio = max(380, y_sku + 60)
                draw_efe_preciador(draw, cx, y_precio, "S/", str(row['Precio desc']), f_ps, f_pv, scale=1.0, tracking=-3)
                
                # --- LEGALES (Fijos en 485) ---
                draw_justified_text(draw, str(row['Legales']), f_l, 485, 40, 960, (255,255,255), line_spacing_offset=0, force_justify=True)
            # 2. LÓGICA PARA IRRESISTIBLE (DISPLAY)
            else:
                # Imagen: 465px, Y=24, X=412
                pi.thumbnail((485, 465))
                img.paste(pi, (412, 24), pi)
                
                lx = 91 # Margen izquierdo
                
                # Marca: Y=219
                draw.text((lx, 219), row['Marca'], font=f_m, fill=(255,255,255), anchor="ls")
                
                # Nombre del producto: 2 filas máximo, interlineado de 25px
                lines_prod = textwrap.wrap(row['Nombre del producto'], width=20)
                ny = 255 
                for lp in lines_prod[:4]:
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

# --- INICIO DE EJECUCIÓN CORREGIDO ---
data, res_sheet, viejos = get_sheets_data()
os.makedirs('output', exist_ok=True)
h_lima = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")

archivos_generados = 0 # <--- INDISPENSABLE para el main.yml

# Ciclo 1: Procesa todos los formatos que NO son FLYER
for idx, row in data.iterrows():
    f_v = str(row['Formato']).upper().strip()
    if f_v in ["FLYER", "", "0"]: continue 
    tienda = str(row.get('Tienda', 'LC')).strip().upper()
    llave = f"{row['SKU']}_{f_v}_{tienda}_EFE".upper()
    
    if llave not in viejos:
        print(f"🎨 Generando: {llave}")
        url = generar_diseno(row)
        if url: 
            res_sheet.append_row([h_lima, llave, tienda, row['Tipo de diseño'], f_v, "EFE", url])
            archivos_generados += 1 # <--- Sumar para avisar a GitHub

# Ciclo 2: Procesa específicamente los FLYERS
fly_g = data[data['Formato'].astype(str).str.upper().str.strip() == "FLYER"]
for id_f, group in fly_g.groupby('ID_Flyer'):
    if str(id_f) in ["0", "0.0", ""]: continue
    llave = f"{id_f}_FLYER_EFE".upper()
    if llave not in viejos:
        print(f"🎨 Generando Flyer: {llave}")
        url = generar_diseno(group)
        if url: 
            res_sheet.append_row([h_lima, llave, "EFE", group.iloc[0]['Tipo de diseño'], "FLYER", "EFE", url])
            archivos_generados += 1 # <--- Sumar para avisar a GitHub

# --- SEGURO ANTI-ERROR PARA GITHUB ACTIONS ---
if archivos_generados == 0:
    print("No se generaron piezas nuevas. Creando placeholder para evitar error de Git.")
    with open("output/placeholder.txt", "w") as f:
        f.write(f"Ejecución sin cambios: {h_lima}")
else:
    print(f"✅ Éxito: Se crearon {archivos_generados} archivos en la carpeta output.")