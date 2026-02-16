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
    # 1. Preparación del prefijo en Negrita (SemiBold)
    prefix = "CONDICIONES GENERALES: "
    if text.startswith("CONDICIONES GENERALES"):
        text = text.replace("CONDICIONES GENERALES:", "").strip()
    
    # Intentamos obtener la versión SemiBold de la fuente actual
    try:
        font_path = font.path.replace("Regular", "SemiBold")
        font_bold = ImageFont.truetype(font_path, font.size)
    except:
        font_bold = font

    container_width = x_end - x_start
    chars_per_line = 135 if container_width > 600 else 68
    
    full_text = prefix + text
    lines = textwrap.wrap(full_text, width=chars_per_line)
    line_height = font.getbbox("Ay")[3] + line_spacing_offset
    
    for i, line in enumerate(lines):
        words = line.split()
        if not words: continue

        # Identificamos si es la última línea o si está muy vacía para NO justificar
        is_last_line = (i == len(lines) - 1)
        line_pixels = sum(draw.textlength(w, font=font) for w in words)
        too_empty = line_pixels < (container_width * 0.7)

        if is_last_line or too_empty or not force_justify:
            # ALINEACIÓN IZQUIERDA (Última línea o línea vacía)
            x_cursor = x_start
            for j, word in enumerate(words):
                # Solo las dos primeras palabras de la primera línea van en Bold
                current_font = font_bold if (i == 0 and j <= 1) else font
                draw.text((x_cursor, y_start), word, font=current_font, fill=fill)
                x_cursor += draw.textlength(word + " ", font=current_font)
        else:
            # JUSTIFICACIÓN MATEMÁTICA (Líneas intermedias llenas)
            total_words_w = sum(draw.textlength(w, font=font_bold if (i == 0 and j <= 1) else font) for j, w in enumerate(words))
            space_width = (container_width - total_words_w) / (len(words) - 1)
            x_cursor = x_start
            for j, word in enumerate(words):
                current_font = font_bold if (i == 0 and j <= 1) else font
                draw.text((x_cursor, y_start), word, font=current_font, fill=fill)
                x_cursor += draw.textlength(word, font=current_font) + space_width
        
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

# Función para dibujar el botón/recuadro naranja del precio ("Eferton")
def draw_efe_preciador(draw, x_center, y_center, text_s, text_price, f_ps, f_pv, scale=1.0, tracking=-2):
    num_w = 0
    # Calcula el ancho total del precio considerando el 'tracking' (espacio entre letras)
    for char in text_price:
        num_w += draw.textlength(char, font=f_pv) + tracking
    num_w -= tracking 
    sym_w = draw.textlength(text_s, font=f_ps)
    # Espacio entre el símbolo de moneda y el número, ajustado por escala
    gap = 8 * scale 
    full_w = sym_w + gap + num_w
    # Altura base del recuadro (110px por defecto)
    h = int(110 * scale) 
    # Dibuja el rectángulo redondeado naranja
    draw.rounded_rectangle([x_center - full_w//2 - 20, y_center - h//2, x_center + full_w//2 + 20, y_center + h//2], 
                           radius=15, fill="#FFA002")
    # Posiciona y dibuja el símbolo de moneda
    tx = x_center - full_w//2
    draw.text((tx, y_center), text_s, font=f_ps, fill=(255,255,255), anchor="lm")
    # Dibuja el precio carácter por carácter para aplicar el tracking manual
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

# --- LÓGICA ESPECÍFICA PARA FORMATO: FLYER (Centrado Dinámico) ---
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
        
        # Definimos la estructura según cantidad de productos
        if num_prod > 6:
            rows = 4
            box_h = 340
            img_size_w, img_size_h = 350, 220 
            preciador_scale = 0.45
        else:
            rows = 3
            box_h = 430 # Altura de caja para 6 productos
            img_size_w, img_size_h = 434, 292
            preciador_scale = 0.55

        # CÁLCULO DE CENTRADO VERTICAL:
        # Sumamos la altura de todas las filas y calculamos el espacio sobrante
        total_content_h = (rows * box_h) + ((rows - 1) * 12)
        # El y_start será el límite superior + la mitad del espacio que sobra
        y_centering_offset = (available_h - total_content_h) // 2
        current_y_top = y_limit_top + y_centering_offset

        for i, (idx, p) in enumerate(data_input.iterrows()):
            if i >= 8: break
            
            # xp se mantiene igual, yp ahora usa el current_y_top calculado
            xp = 65 + (i % 2) * 495
            yp = current_y_top + (i // 2) * (box_h + 12)
            
            # Pegado de imagen centrada en su espacio
            try:
                url_foto = p.get('Foto del producto calado') or p.get('Foto')
                if url_foto:
                    pi_res = requests.get(url_foto, timeout=10)
                    pi_fly = Image.open(BytesIO(pi_res.content)).convert("RGBA")
                    pi_fly.thumbnail((img_size_w, img_size_h))
                    ix = int(xp + 240 - pi_fly.width // 2)
                    iy = int(yp + 20) 
                    img.paste(pi_fly, (ix, iy), pi_fly)
            except: pass

            # --- COLUMNAS IMAGINARIAS ---
            cx_col1, cx_col2 = xp + 125, xp + 345
            
            # Columna 1: Marca y Nombre
            f_m_flyer = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 30)
            draw.text((cx_col1, yp + box_h - 110), p['Marca'], font=f_m_flyer, fill=(0,0,0), anchor="mm")
            draw.text((cx_col1, yp + box_h - 75), p['Nombre del producto'][:18], font=f_p, fill=(0,0,0), anchor="mm")
            
            # Columna 2: Precio y SKU
            f_pv_fly = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 53)
            f_ps_fly = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 30)
            y_precio = yp + box_h - 85 
            
            if "EFERTON" in tipo:
                draw_efe_preciador(draw, cx_col2, y_precio, "S/", str(p['Precio desc']), f_ps_fly, f_pv_fly, scale=preciador_scale)
            else:
                w_s = draw.textlength("S/", font=f_ps_fly)
                draw.text((cx_col2 - 40, y_precio), "S/", font=f_ps_fly, fill="#FFA002", anchor="ls")
                draw.text((cx_col2 - 40 + w_s + 5, y_precio), str(p['Precio desc']), font=f_pv_fly, fill="#FFA002", anchor="ls")

            draw.text((cx_col2, y_precio + 45), f"SKU: {p['SKU']}", font=f_s_ind, fill=(0,0,0), anchor="mm")
            
            # Divisores
            line_c = "#00ACDE" if "EFERTON" in tipo else "#0A74DA"
            if i % 2 == 0 and (i + 1) < num_prod: 
                draw_dotted_line(draw, (xp+475, yp+20), (xp+475, yp+box_h-20), line_c)
        
        # Legales Flyer (Asegúrate de agregar el force_justify=True al final)
        l_margin = 70 if "EFERTON" in tipo else 62
        f_l_flyer = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", l_size + 2)
        
        # Agregamos force_justify=True para que se vea como bloque cuadrado
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
                pi.thumbnail((747, 270))
                img.paste(pi, (126, 269), pi)
                
                # --- COLUMNAS IMAGINARIAS (Y base ajustada con los +70, +52, +80) ---
                
                # COLUMNA 1: MARCA (Comienza en X=90, Y=900)
                f_m_efe = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 30) # -2pts de los 32 originales
                draw.text((90, 900), row['Marca'], font=f_m_efe, fill=(255,255,255), anchor="ls")
                
                # COLUMNA 2: NOMBRE Y SKU (Centro del banner X=500, pero bajados)
                # Nombre: 830 + 15 (original) + 52 (pedido) = 897 
                f_p_efe = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 25)
                draw.text((500, 897), row['Nombre del producto'][:25], font=f_p_efe, fill=(255,255,255), anchor="mm")
                
                # SKU: 830 + 55 (original) + 52 (pedido) = 937
                f_s_efe = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 22)
                draw.text((500, 937), str(row['SKU']), font=f_s_efe, fill=(255,255,255), anchor="mm")
                
                # COLUMNA 3: PRECIO (X=840, Y=910)
                # 830 + 80 (pedido) = 910. El "S/" se alinea solo dentro de la función del preciador.
                draw_efe_preciador(draw, 840, 910, "S/", str(row['Precio desc']), f_ps, f_pv, scale=1.0, tracking=-3)
                
                # LEGALES: Y=998 (980+18), Margen 90px (X_ini=90, X_fin=910)
                # force_justify=False para que no se vea tan separado
                draw_justified_text(draw, str(row['Legales']), f_l, 998, 90, 910, (255,255,255), line_spacing_offset=1, force_justify=True)
                
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
                
                # Alineación al ras (Y=800 aprox, ajustado para que quepa sobre legales)
                py = 830 
                w_s = draw.textlength("S/", font=f_ps44)
                draw.text((lx, py), "S/", font=f_ps44, fill=(255,255,255), anchor="ls")
                draw.text((lx + w_s + 10, py), str(row['Precio desc']), font=f_pv80, fill=(255,255,255), anchor="ls")
                
                # Legales Irresistible: Margen 73px (X_ini=73, X_fin=927), Y=937
                draw_justified_text(draw, str(row['Legales']), f_l, 937, 73, 927, (255,255,255), line_spacing_offset=0, force_justify=True)

 # --- FORMATO: STORY (9:16 - Ajustes Eferton e Irresistible) ---
        elif formato == "STORY":
            # 1. LÓGICA PARA EFERTON
            if "EFERTON" in tipo:
                # Imagen: 936px por lado, X=72, Y=606
                pi.thumbnail((936, 936))
                img.paste(pi, (72, 606), pi)
                
                # Posiciones de texto
                # Marca: mantenemos el centro relativo o izquierda según diseño anterior, 
                # pero Nombre Producto ahora en X=239
                ay = 1600 
                draw.text((239, ay), row['Marca'], font=f_m, fill=(255,255,255), anchor="ls")
                draw.text((239, ay+55), row['Nombre del producto'][:30], font=f_p, fill=(255,255,255), anchor="ls")
                draw.text((239, ay+100), str(row['SKU']), font=f_s_ind, fill=(255,255,255), anchor="ls")
                
                # Precio: 110pts, S/ 64pts. Ubicación S/ en X=613, Y=1614
                f_pv_efe = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 110)
                f_ps_efe = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 64)
                
                # Dibujamos S/ y Precio a ras en Y=1614
                draw.text((613, 1614), "S/", font=f_ps_efe, fill=(255,255,255), anchor="ls")
                w_s = draw.textlength("S/", font=f_ps_efe)
                draw.text((613 + w_s + 12, 1614), str(row['Precio desc']), font=f_pv_efe, fill=(255,255,255), anchor="ls")
                
                # Legales Eferton: Y=1800, Margen 70 (X_ini=70, X_fin=1010), Tamaño +2pts
                f_l_story = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", l_size + 2)
                draw_justified_text(draw, str(row['Legales']), f_l_story, 1800, 70, 1010, (255,255,255), line_spacing_offset=1, force_justify=True)

            # 2. LÓGICA PARA IRRESISTIBLE
            else:
                # Imagen: 905px por lado, X=76, Y=596
                pi.thumbnail((905, 905))
                img.paste(pi, (76, 596), pi)
                
                lx = 147 # Margen izquierdo solicitado
                
                # Marca: X=147, Y=1563, Tamaño 46pts
                f_m_irr = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 46)
                draw.text((lx, 1563), row['Marca'], font=f_m_irr, fill=(255,255,255), anchor="ls")
                
                # Nombre Producto: 38pts, 2 líneas, hasta X=506 (aprox 16-18 caracteres por línea)
                f_p_irr = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 38)
                lines_prod = textwrap.wrap(row['Nombre del producto'], width=18)
                ny = 1615
                for lp in lines_prod[:2]:
                    draw.text((lx, ny), lp, font=f_p_irr, fill=(255,255,255), anchor="ls")
                    ny += 42 # Salto de línea
                
                # SKU: 29pts
                f_s_irr = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 29)
                draw.text((lx, ny + 10), str(row['SKU']), font=f_s_irr, fill=(255,255,255), anchor="ls")
                
                # Precio: S/ 71pts, Número 128pts, X=566, Y=1658 (a ras)
                f_pv_irr = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 128)
                f_ps_irr = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 71)
                
                draw.text((566, 1658), "S/", font=f_ps_irr, fill=(255,255,255), anchor="ls")
                w_s_irr = draw.textlength("S/", font=f_ps_irr)
                draw.text((566 + w_s_irr + 15, 1658), str(row['Precio desc']), font=f_pv_irr, fill=(255,255,255), anchor="ls")
                
                # Legales Irresistible: Y=109 (esta posición es arriba según tu pedido), 
                # Margen 70 (X_ini=70, X_fin=1010), Letra +2pts, force_justify=False
                f_l_story = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", l_size + 2)
                draw_justified_text(draw, str(row['Legales']), f_l_story, 109, 70, 1010, (255,255,255), line_spacing_offset=1, force_justify=True)

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
                draw_justified_text(draw, str(row['Legales']), f_l, 490, 40, 960, (255,255,255), line_spacing_offset=-1, force_justify=True)

            # 2. LÓGICA PARA IRRESISTIBLE
            else:
                # Imagen: 465px, Y=24, X=412
                pi.thumbnail((465, 465))
                img.paste(pi, (412, 24), pi)
                
                # Alineación a la izquierda: X=91
                lx = 91
                
                # Marca: Y=219
                draw.text((lx, 219), row['Marca'], font=f_m, fill=(255,255,255), anchor="ls")
                
                # Nombre del producto: 2 filas máximo, alineado a la izquierda (lx=91)
                lines_prod = textwrap.wrap(row['Nombre del producto'], width=20)
                ny = 255 # Posición inicial debajo de la marca
                for lp in lines_prod[:2]:
                    draw.text((lx, ny), lp, font=f_p, fill=(255,255,255), anchor="ls")
                    ny += 25
                
                # SKU: Justo debajo del nombre
                draw.text((lx, ny + 5), str(row['SKU']), font=f_s_ind, fill=(255,255,255), anchor="ls")
                
                # Precio Irresistible: Extrabold, Precio 76pt, S/ 42pt, X=91, Y=364
                f_pv_irr = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 76)
                f_ps_irr = ImageFont.truetype(f"{path_fonts}/Poppins-ExtraBold.ttf", 42)
                
                w_s_irr = draw.textlength("S/", font=f_ps_irr)
                draw.text((lx, 364), "S/", font=f_ps_irr, fill=(255,255,255), anchor="ls")
                draw.text((lx + w_s_irr + 10, 364), str(row['Precio desc']), font=f_pv_irr, fill=(255,255,255), anchor="ls")
                
                # Legales Irresistible: Y=490, Margen 40 (X_ini=40, X_fin=960 si el ancho es 1000)
                # X_fin = Ancho total - margen de 40. Asumiendo banner de 1000px -> 960.
                draw_justified_text(draw, str(row['Legales']), f_l, 490, 40, 960, (255,255,255), line_spacing_offset=-1, force_justify=True)


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