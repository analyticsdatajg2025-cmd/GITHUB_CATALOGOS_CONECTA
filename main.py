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

def draw_justified_text(draw, text, font, y_start, x_start, x_end, fill, line_spacing_offset=0, force_justify=True):
    """
    Controla el bloque de legales.
    y_start: Altura inicial.
    x_start: Margen izquierdo (donde empieza el texto).
    x_end: Margen derecho (donde termina el texto).
    line_spacing_offset: Espacio entre filas (negativo para juntarlas).
    """
    if not text.startswith("CONDICIONES GENERALES"):
        text = "CONDICIONES GENERALES: " + text
        
    # width controla el salto de línea automático según el ancho del contenedor
    lines = textwrap.wrap(text, width=135 if (x_end - x_start) > 600 else 65)
    line_height = font.getbbox("Ay")[3] + line_spacing_offset
    
    for i, line in enumerate(lines):
        words = line.split()
        # force_justify=False evita espacios gigantes si hay pocas palabras
        if i == len(lines) - 1 or len(words) <= 1 or not force_justify:
            draw.text((x_start, y_start), line, font=font, fill=fill)
        else:
            # Distribución matemática de espacios para tocar ambos márgenes
            total_words_w = sum(draw.textlength(w, font=font) for w in words)
            space_width = ((x_end - x_start) - total_words_w) / (len(words) - 1)
            x_cursor = x_start
            for word in words:
                draw.text((x_cursor, y_start), word, font=font, fill=fill)
                x_cursor += draw.textlength(word, font=font) + space_width
        y_start += line_height

def draw_dotted_line(draw, start, end, fill, width=2, gap=8):
    """Dibuja las líneas punteadas decorativas."""
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

def draw_efe_preciador(draw, x_center, y_center, text_s, text_price, f_ps, f_pv, scale=1.0, tracking=-2):
    """
    Dibuja el recuadro naranja con el precio.
    scale: Tamaño general del recuadro.
    tracking: Qué tan pegados están los números del precio.
    """
    num_w = 0
    for char in text_price:
        num_w += draw.textlength(char, font=f_pv) + tracking
    num_w -= tracking 
    sym_w = draw.textlength(text_s, font=f_ps)
    gap = 8 * scale # Espacio entre el S/ y el número
    full_w = sym_w + gap + num_w
    h = int(110 * scale) # Altura del recuadro
    draw.rounded_rectangle([x_center - full_w//2 - 20, y_center - h//2, x_center + full_w//2 + 20, y_center + h//2], 
                           radius=15, fill="#FFA002")
    tx = x_center - full_w//2
    draw.text((tx, y_center), text_s, font=f_ps, fill=(255,255,255), anchor="lm")
    curr_x = tx + sym_w + gap
    for char in text_price:
        draw.text((curr_x, y_center), char, font=f_pv, fill=(255,255,255), anchor="lm")
        curr_x += draw.textlength(char, font=f_pv) + tracking

def get_sheets_data():
    """Conexión con Google Sheets."""
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

    # --- DEFINICIÓN DE FONDO (Lienzo principal) ---
    f_names = [f"{tienda} - {tipo} - {formato}", f"{tienda} - REPOWER {tipo} - {formato}"]
    full_p = next((os.path.join(path_fondos, f"{v}{e}") for v in f_names for e in [".jpg", ".png", ".JPG"] if os.path.exists(os.path.join(path_fondos, f"{v}{e}"))), None)
    
    if not full_p: return None
    img = Image.open(full_p).convert("RGB")
    draw = ImageDraw.Draw(img)

    # --- CONFIGURACIÓN DE TAMAÑOS DE FUENTE (Aumentar/Disminuir aquí) ---
    try:
        p_size = 90; s_size = 35; l_size = 10
        if formato == "DISPLAY": 
            p_size = 50; s_size = 20; l_size = 7 # l_size=9 es el aumento de 3pt solicitado
        elif formato == "STORY": 
            p_size = 100; s_size = 40
        elif formato == "FLYER":
            p_size = 50; s_size = 25
        
        f_m = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 44 if formato == "STORY" else 32)
        f_p = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 30 if formato == "STORY" else 20)
        f_pv = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", p_size) # Precio
        f_ps = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", s_size) # S/
        f_s_ind = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 18 if formato == "STORY" else 15) # SKU
        f_l = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", l_size) # Legales
        f_f = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 26) # Fecha Flyer
    except: f_m = f_p = f_pv = f_ps = f_s_ind = f_l = f_f = ImageFont.load_default()

# --- FORMATO: FLYER ADAPTATIVO (6 vs 8 productos) ---
    if formato == "FLYER":
        f_txt = str(row['Fecha_disponibilidad_flyer']).upper()
        draw.text((540, 260), f_txt, font=f_f, fill=(255,255,255), anchor="mm")
        
        num_prod = len(data_input)
        # 1. Definimos dimensiones según la cantidad de productos
        if num_prod > 6:
            box_h, img_size, preciador_scale = 330, 250, 0.5
        else:
            box_h, img_size, preciador_scale = 450, 330, 0.6 # Más grande para 6 productos
            
        for i, (idx, p) in enumerate(data_input.iterrows()):
            if i >= 8: break
            # xp y yp calculan la rejilla
            xp, yp = 65+(i%2)*495, 345+(i//2)*(box_h+12)
            
            line_c = "#00ACDE" if "EFERTON" in tipo else "#0A74DA"
            
            # LÍNEA VERTICAL: Solo si hay un producto a la derecha
            if i % 2 == 0 and (i + 1) < num_prod: 
                draw_dotted_line(draw, (xp+475, yp+20), (xp+475, yp+box_h-20), line_c)
            
            # LÍNEA HORIZONTAL: Solo si hay una fila debajo (evita línea fantasma en 6 productos)
            if (i + 2) < num_prod: 
                draw_dotted_line(draw, (xp+20, yp+box_h+6), (xp+435, yp+box_h+6), line_c)

            # --- CORRECCIÓN DE IMAGEN ---
            try:
                # Usamos p.get para evitar errores si la columna cambia de nombre ligeramente
                url_foto = p.get('Foto del producto calado') or p.get('Foto')
                if url_foto:
                    pi_res = requests.get(url_foto, timeout=10)
                    pi_fly = Image.open(BytesIO(pi_res.content)).convert("RGBA")
                    
                    # Redimensionamos con el tamaño dinámico
                    pi_fly.thumbnail((img_size, img_size))
                    
                    # Cálculo de posición CENTRADA (usando int() para asegurar que PIL lo acepte)
                    x_pos = int(xp + 240 - pi_fly.width // 2)
                    y_pos = int(yp + (box_h // 2.4) - pi_fly.height // 2)
                    
                    img.paste(pi_fly, (x_pos, y_pos), pi_fly)
            except Exception as e:
                print(f"Error en imagen {i}: {e}")

            # --- TEXTOS POSICIONADOS RELATIVOS AL FINAL DE LA CAJA ---
            cx_l = xp + 125
            draw.text((cx_l, yp+box_h-113), p['Marca'], font=f_m, fill=(0,0,0), anchor="mm")
            draw.text((cx_l, yp+box_h-83), p['Nombre del producto'][:20], font=f_p, fill=(0,0,0), anchor="mm")
            draw.text((cx_l, yp+box_h-58), str(p['SKU']), font=f_s_ind, fill=(0,0,0), anchor="mm")
            
            if "EFERTON" in tipo: 
                draw_efe_preciador(draw, xp+345, yp+box_h-75, "S/", str(p['Precio desc']), f_ps, f_pv, scale=preciador_scale, tracking=-2)
            else:
                # Precio normal con S/ pequeño
                w_s = draw.textlength("S/", font=f_ps)
                draw.text((xp+305, yp+box_h-75), "S/", font=f_ps, fill="#FFA002", anchor="lm")
                draw.text((xp+305 + w_s + 6, yp+box_h-75), str(p['Precio desc']), font=f_pv, fill="#FFA002", anchor="lm")
        
        draw_justified_text(draw, str(row['Legales']), f_l, 1835, 65, 1015, (255,255,255), line_spacing_offset=1)

    # --- FORMATOS: PPL, STORY, DISPLAY ---
    else:
        headers = {'User-Agent': 'Mozilla/5.0'}
        pi_res = requests.get(row['Foto del producto calado'], headers=headers, timeout=10)
        pi = Image.open(BytesIO(pi_res.content)).convert("RGBA")
        
        # 1. PPL
        if formato == "PPL":
            if "EFERTON" in tipo:
                # Imagen un poco más grande para llenar el espacio
                pi.thumbnail((650, 650)) 
                img.paste(pi, (500-pi.width//2, 525-pi.height//2), pi)
                
                ay = 830 
                
                # --- AJUSTE DE TAMAÑOS (Aumentados) ---
                f_m_efe = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 40) # Antes 45
                f_p_efe = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 28) # Antes 35
                f_s_efe = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 22) # SKU nuevo, más grande
                
                # Dibujo de textos con las nuevas fuentes
                draw.text((165, ay), row['Marca'], font=f_m_efe, fill=(255,255,255), anchor="mm")
                
                # Nombre del producto (Bajamos un poco el Y a ay+15 para dar aire a la marca más grande)
                draw.text((500, ay+15), row['Nombre del producto'][:25], font=f_p_efe, fill=(255,255,255), anchor="mm")
                
                # SKU (Bajamos a ay+55 para que no choque con el nombre)
                draw.text((500, ay+55), str(row['SKU']), font=f_s_efe, fill=(255,255,255), anchor="mm")
                
                # Preciador Eferton (Mantenemos scale=1.0 por los nuevos tamaños de texto)
                draw_efe_preciador(draw, 840, ay, "S/", str(row['Precio desc']), f_ps, f_pv, scale=1.0, tracking=-3)
                
                # Legales
                draw_justified_text(draw, str(row['Legales']), f_l, 980, 50, 970, (255,255,255), line_spacing_offset=1)
            else: 
                # PPL PRECIO IRRESISTIBLE
                # Imagen: 80px Izquierda (490) y 70px Abajo (640)
                pi.thumbnail((730, 730)); img.paste(pi, (660-pi.width//2, 640-pi.height//2), pi)
                ay = 720 
                draw.text((100, ay), row['Marca'], font=f_m, fill=(255,255,255), anchor="lm")
                # Producto en 2 filas
                lines_prod = textwrap.wrap(row['Nombre del producto'], width=18)
                ny = ay + 35
                for lp in lines_prod[:2]:
                    draw.text((100, ny), lp, font=f_p, fill=(255,255,255), anchor="lm"); ny += 25
                draw.text((100, ny + 10), str(row['SKU']), font=f_s_ind, fill=(255,255,255), anchor="lm")
                
                f_pv80 = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 80)
                f_ps40 = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 40)
                draw.text((100, ny + 70), "S/", font=f_ps40, fill=(255,255,255), anchor="lm")
                draw.text((100 + 70, ny + 70), str(row['Precio desc']), font=f_pv80, fill=(255,255,255), anchor="lm")
                # Legales PPL Irresistible: Y=995 (Bajado 10px), márgenes 50 a 950
                draw_justified_text(draw, str(row['Legales']), f_l, 1010, 80, 970, (255,255,255), line_spacing_offset=0)

        # 2. STORY (Mantenido intacto)
        elif formato == "STORY":
            pi.thumbnail((1000, 1000)); img.paste(pi, (540-pi.width//2, 630), pi)
            ay = 1600 
            draw.text((280, ay), row['Marca'], font=f_m, fill=(255,255,255), anchor="mm")
            draw.text((280, ay+50), row['Nombre del producto'][:30], font=f_p, fill=(255,255,255), anchor="mm")
            draw.text((280, ay+85), str(row['SKU']), font=f_s_ind, fill=(255,255,255), anchor="mm")
            if "EFERTON" in tipo:
                draw_efe_preciador(draw, 810, ay+50, "S/", str(row['Precio desc']), f_ps, f_pv, scale=1.1, tracking=-4)
            else:
                w_tot = draw.textlength("S/", font=f_ps) + 12 + draw.textlength(str(row['Precio desc']), font=f_pv)
                cx = 810 - w_tot // 2
                draw.text((cx, ay+50), "S/", font=f_ps, fill=(255,255,255), anchor="lm")
                draw.text((cx + draw.textlength("S/", font=f_ps) + 12, ay+50), str(row['Precio desc']), font=f_pv, fill=(255,255,255), anchor="lm")
            draw_justified_text(draw, str(row['Legales']), f_l, 1835, 65, 1015, (255,255,255), line_spacing_offset=1)

        # 3. DISPLAY
        elif formato == "DISPLAY":
            pi.thumbnail((520, 520))
            if "IRRESISTIBLE" in tipo: img.paste(pi, (470, 70), pi)
            else: img.paste(pi, (480, 70), pi)
            cx = 260 # Centro del área de texto
            # Bajado +10px (220->230, 260->270, 290->300)
            draw.text((cx, 250), row['Marca'], font=f_m, fill=(255,255,255), anchor="mm")
            draw.text((cx, 290), row['Nombre del producto'][:25], font=f_p, fill=(255,255,255), anchor="mm")
            draw.text((cx, 320), str(row['SKU']), font=f_s_ind, fill=(255,255,255), anchor="mm")
            # Precio subido -5px (405->400)
            if "EFERTON" in tipo:
                draw_efe_preciador(draw, cx, 380, "S/", str(row['Precio desc']), f_ps, f_pv, scale=0.5, tracking=-3)
            else:
                w_s = draw.textlength("S/", font=f_ps)
                w_p = draw.textlength(str(row['Precio desc']), font=f_pv)
                start_x = cx - (w_s + 10 + w_p) // 2
                draw.text((start_x, 380), "S/", font=f_ps, fill=(255,255,255), anchor="lm")
                draw.text((start_x + w_s + 10, 380), str(row['Precio desc']), font=f_pv, fill=(255,255,255), anchor="lm")
            # Legales Display: Márgenes 40 a 480 (Mitad del banner), force_justify=False para legibilidad
            draw_justified_text(draw, str(row['Legales']), f_l, 465, 44, 520, (255,255,255), line_spacing_offset=-1, force_justify=True)

    # --- GUARDADO FINAL ---
    fname = f"{row['SKU'] or row['ID_Flyer']}_{formato}_{tienda}.jpg"
    img.save(f"output/{fname}", quality=95); return f"{RAW_URL}{fname}"

# --- INICIO DE EJECUCIÓN ---
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
