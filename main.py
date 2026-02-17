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
    # Ajuste dinámico de envoltura según el ancho del contenedor
    wrap_width = 45 if available_w < 500 else 110 
    lines = textwrap.wrap(text, width=wrap_width)
    
    y = y_start
    # Medimos cuánto mide un espacio normal en la fuente elegida
    normal_space_w = draw.textlength(" ", font=font)
    
    for i, line in enumerate(lines):
        words = line.split()
        if not words: continue

        # Ajuste inicial para la primera línea si existe un prefijo (ej. "CONDICIONES GENERALES")
        current_x_start = x_start + (prefix_width if i == 0 else 0)
        current_available_w = available_w - (prefix_width if i == 0 else 0)
        
        # --- CÁLCULO DE JUSTIFICACIÓN ---
        total_text_w = sum(draw.textlength(w, font=font) for w in words)
        num_gaps = len(words) - 1
        
        # Calculamos el ancho de espacio necesario para justificar
        target_space_w = (current_available_w - total_text_w) / num_gaps if num_gaps > 0 else 0
        
        # CONDICIÓN DE SEGURIDAD PARA ALINEAR A LA IZQUIERDA:
        # 1. Es la última línea del párrafo.
        # 2. Solo hay una palabra en la línea.
        # 3. El espacio necesario es más de 2.5 veces el normal (evita huecos feos).
        if i == len(lines) - 1 or len(words) <= 1 or target_space_w > (normal_space_w * 2.5):
            draw.text((current_x_start, y), line, font=font, fill=fill)
        else:
            # LÍNEAS INTERMEDIAS CON ESPACIADO RAZONABLE: Justificamos
            curr_x = current_x_start
            for word in words:
                draw.text((curr_x, y), word, font=font, fill=fill)
                curr_x += draw.textlength(word, font=font) + target_space_w
        
        # Salto de línea dinámico según el alto de la fuente
        y += font.getbbox("Ay")[3] + line_spacing
        
def get_sheets_data():
    """Conexión con Google Sheets para traer datos de productos."""
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
    
    # Colores según versión
    txt_c = (0,0,0) if color_version == "AMARILLO" else (255,255,255)
    border_c = (254, 215, 0) if color_version == "AMARILLO" else (10, 6, 60)
    accent_date = (0,0,0) if color_version == "AMARILLO" else (255,255,255)

    # Carga de imagen de fondo
    fname_base = f"LC - {tipo} - {'FLYER' if formato == 'FLYER' else formato}"
    full_p = next((os.path.join(path_fondos, f"{v}{e}") for v in [f"{fname_base} FONDO {color_version}", f"{fname_base} {color_version}", fname_base] for e in [".png", ".jpg", ".PNG", ".JPG"] if os.path.exists(os.path.join(path_fondos, f"{v}{e}"))), None)
    if not full_p: return None
    img = Image.open(full_p).convert("RGB"); draw = ImageDraw.Draw(img)

    try:
        # --- CARGA INICIAL DE FUENTES COMUNES ---
        f_f = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 24) # Fuente Fecha
        
        # --- AJUSTE DE TAMAÑOS POR FORMATO ---
        if formato == "STORY":
            f_m = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 53)
            f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 32)
            f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 106)
            f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 42)
            f_s_ind = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 18)
            f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 14)
        elif formato == "PPL":
            f_m = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 43)
            f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 23)
            f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 85)
            f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 36)
            f_s_ind = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 14)
            f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 13)
        elif formato == "FLYER":
            f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 73) 
            f_s_fly = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 13)    
            f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 16)
            f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 18)
            # --- AGREGADO f_ps AQUÍ PARA EVITAR EL ERROR ---
            f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 30) 
        else: # DISPLAY
            f_m = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 34)
            f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 20)
            f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 75)
            f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 30)
            f_s_ind = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 13)
            f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 9)
            
    except: 
        # Aseguramos que todas las variables existan en caso de error de carga
        f_m = f_p = f_pv = f_ps = f_s_ind = f_s_fly = f_f = f_l = ImageFont.load_default()
        
# --- LÓGICA DE POSICIONAMIENTO FLYER (Múltiples productos) ---
    if formato == "FLYER":
        # 1. Fecha (Margen x=64)
        f_txt = str(row['Fecha_disponibilidad_flyer']).upper()
        wf = draw.textlength(f_txt, font=f_f)
        x_fecha = 64 
        draw.rounded_rectangle([x_fecha, 235, x_fecha+wf+35, 285], radius=10, outline=accent_date, width=3)
        draw.text((x_fecha+(wf+35)//2, 260), f_txt, font=f_f, fill=accent_date, anchor="mm")
        
        # 2. Configuración de Cuadrícula DINÁMICA
        num_productos = len(data_input)
        
        # MEDIDAS ORIGINALES PARA 6 PRODUCTOS (Tus medidas)
        if num_productos <= 6:
            box_w, box_h = 456, 456
            img_size = 338
            gap_y = 30
            y_offset_img = 20
        # AJUSTE EXCLUSIVO PARA 8 PRODUCTOS PARA QUE NO PISEN LEGALES
        else:
            box_w, box_h = 456, 375  # Reducimos alto de caja
            img_size = 250           # Reducimos imagen para ganar espacio
            gap_y = 15               # Espacio entre cuadros más compacto
            y_offset_img = 10

        for i, (idx, p) in enumerate(data_input.iterrows()):
            if i >= 8: break
            
            xp = 64 + (i % 2) * (box_w + 40)
            yp = 320 + (i // 2) * (box_h + gap_y)
            
            # Dibujar Caja
            draw.rounded_rectangle([xp, yp, xp+box_w, yp+box_h], radius=15, fill=(255,255,255), outline=border_c, width=2)
            
            # Imagen del producto (Escalada según el caso)
            try:
                pi_url = p['Foto del producto calado']
                pi = Image.open(BytesIO(requests.get(pi_url).content)).convert("RGBA")
                pi.thumbnail((img_size, img_size), Image.Resampling.LANCZOS)
                # Centrado horizontal dinámico
                img.paste(pi, (int(xp + (box_w - pi.width) // 2), int(yp + y_offset_img)), pi)
            except: pass
            
            # Ejes para textos
            cl, cr = xp + 114, xp + 342
            
            # Marca y Nombre (Posición relativa al fondo de la caja actual)
            y_marca_prod = yp + box_h - 86 
            f_m_fly = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 20 if len(p['Marca']) < 12 else 16)
            draw.text((cl, y_marca_prod), p['Marca'], font=f_m_fly, fill=(0,0,0), anchor="mm")
            
            ny = y_marca_prod + 25 
            for ln in textwrap.wrap(p['Nombre del producto'], width=18)[:2]:
                draw.text((cl, ny), ln, font=f_p, fill=(0,0,0), anchor="mm")
                ny += 20
            
            # Precio y SKU (Posición relativa al fondo de la caja actual)
            y_precio = yp + box_h - 57
            p_val = str(p['Precio desc'])
            tw_p = draw.textlength("S/", font=f_ps) + draw.textlength(p_val, font=f_pv) + 8
            px_inicio = cr - tw_p // 2
            
            draw.text((px_inicio, y_precio), "S/", font=f_ps, fill=(0,0,0), anchor="lm")
            draw.text((px_inicio + draw.textlength("S/", font=f_ps) + 8, y_precio), p_val, font=f_pv, fill=(0,0,0), anchor="lm")
            
            draw.text((cr, y_precio + 35), str(p['SKU']), font=f_s_fly, fill=(110,110,110), anchor="mm")
            
        # 3. Legales Fijos (Se quedan en 1840)
        y_legales_fijo = 1840 
        f_l_bold = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 16)
        tit_legal = "CONDICIONES GENERALES: "
        cuerpo_legal = str(row['Legales'])
        ancho_negrita = draw.textlength(tit_legal, font=f_l_bold)
        
        draw.text((64, y_legales_fijo), tit_legal, font=f_l_bold, fill=txt_c)
        draw_justified_text(draw, cuerpo_legal, f_l, y_legales_fijo, 64, 1016, txt_c, line_spacing=2, prefix_width=ancho_negrita)

    # --- LÓGICA DE POSICIONAMIENTO FORMATOS INDIVIDUALES ---
    else:
        pi = Image.open(BytesIO(requests.get(row['Foto del producto calado']).content)).convert("RGBA")
        
        if formato == "DISPLAY":
            # --- CONFIGURACIÓN DE IMAGEN ---
            # Tamaño 473px, x=123, y=25
            pi.thumbnail((473, 473))
            img.paste(pi, (423, 25), pi) 

            # --- POSICIONAMIENTO DE TEXTOS (Marca, Nombre, Precio, SKU) ---
            # Centros ajustados: -10px en X, +10px en Y
            cx, ny = 255, 245 

            # Marca
            draw.text((cx, 195), row['Marca'], font=f_m, fill=txt_c, anchor="mt")

            # Nombre del producto (Máximo 2 filas)
            lineas_nombre = textwrap.wrap(row['Nombre del producto'], width=22)[:2]
            for l in lineas_nombre:
                draw.text((cx, ny), l, font=f_p, fill=txt_c, anchor="mt")
                ny += 27 

            # Precio desc
            tw = draw.textlength("S/", font=f_ps) + draw.textlength(str(row['Precio desc']), font=f_pv) + 15
            px = cx - tw//2
            draw.text((px, ny + 55), "S/ ", font=f_ps, fill=txt_c, anchor="lm")
            draw.text((px + draw.textlength("S/ ", font=f_ps) + 15, ny + 55), str(row['Precio desc']), font=f_pv, fill=txt_c, anchor="lm")

            # SKU
            draw.text((cx, ny + 100), str(row['SKU']), font=f_s_ind, fill=txt_c, anchor="mt")

            # --- CONFIGURACIÓN DE LEGALES (JUSTIFICADO CON NEGRITA) ---
            f_l_bold = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 9)
            tit_legal = "CONDICIONES GENERALES: "
            cuerpo_legal = str(row['Legales'])

            # Calculamos el ancho de la negrita para pasarla como 'prefix_width'
            ancho_negrita = draw.textlength(tit_legal, font=f_l_bold)

            # Dibujamos el título en negrita
            draw.text((40, 489), tit_legal, font=f_l_bold, fill=txt_c)

            # Llamamos a la función para el cuerpo del texto legal
            # Usamos prefix_width para que la primera línea empiece después de la negrita
            draw_justified_text(
                draw, cuerpo_legal, f_l, 
                y_start=489, x_start=40, x_end=960, 
                fill=txt_c, line_spacing=2, prefix_width=ancho_negrita
            )  
        
        elif formato == "STORY":
            # --- CONFIGURACIÓN DE IMAGEN ---
            # Se mantiene el tamaño y posición solicitada
            pi = pi.resize((805, 805), Image.Resampling.LANCZOS)
            img.paste(pi, (140, 630), pi)

            # --- POSICIONAMIENTO DE TEXTOS (MARCA Y PRODUCTO) ---
            cx_textos = 150 
            anchor_y_textos = 1482 

            # Marca
            draw.text((cx_textos, anchor_y_textos), row['Marca'], font=f_m, fill=txt_c, anchor="lt")
            
            # --- LÓGICA DE NOMBRE DEL PRODUCTO (MÁXIMO 2 FILAS) ---
            # Reducimos width a 22 para asegurar un margen límite y que no choque con el precio
            ny = anchor_y_textos + 65 
            lineas_nombre = textwrap.wrap(row['Nombre del producto'], width=22)[:2]
            for l in lineas_nombre:
                draw.text((cx_textos, ny), l, font=f_p, fill=txt_c, anchor="lt")
                ny += 40 

            # --- POSICIONAMIENTO DE PRECIO ---
            # Bajamos ambos 10px: 1516 + 10 = 1526
            anchor_y_precio = 1526 
            
            p_v = str(row['Precio desc'])
            # Aumentamos la separación entre S/ y el número a 60px
            espacio_entre_simbolo = 60
            tw = draw.textlength("S/", font=f_ps) + draw.textlength(p_v, font=f_pv) + espacio_entre_simbolo
            
            # Calculamos el punto de inicio para que el conjunto esté centrado en el eje x=810
            px_bloque_completo = 810 - tw//2
            
            # Dibujamos el S/ y el Precio al mismo ras (anchor "ls" -> Left Baseline)
            # Esto corrige que el S/ se vea más arriba que el número
            draw.text((px_bloque_completo, anchor_y_precio), "S/", font=f_ps, fill=txt_c, anchor="ls")
            
            # Calculamos la posición X del número sumando el símbolo y el nuevo espacio
            px_numero = px_bloque_completo + draw.textlength("S/", font=f_ps) + espacio_entre_simbolo
            draw.text((px_numero, anchor_y_precio), p_v, font=f_pv, fill=txt_c, anchor="ls")

            # --- SKU ---
            # Centrado exactamente debajo del bloque de precio (Eje 810)
            # Bajamos la posición para que no se pegue al precio (anchor_y_precio + 60)
            draw.text((810, anchor_y_precio + 60), str(row['SKU']), font=f_s_ind, fill=txt_c, anchor="mt") 

            # --- CONFIGURACIÓN DE LEGALES (Se mantiene igual) ---
            f_l_bold = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 14)
            tit_legal = "CONDICIONES GENERALES: "
            cuerpo_legal = str(row['Legales'])
            
            ancho_negrita = draw.textlength(tit_legal, font=f_l_bold)
            draw.text((65, 1802), tit_legal, font=f_l_bold, fill=txt_c)

            draw_justified_text(
                draw, cuerpo_legal, f_l, 
                y_start=1802, x_start=65, x_end=1015, 
                fill=txt_c, line_spacing=2, prefix_width=ancho_negrita
            )
    
        elif formato == "PPL":
            # --- CONFIGURACIÓN DE IMAGEN (SIN DEFORMACIÓN) ---
            # Usamos thumbnail para mantener la proporción original del producto
            # El área máxima permitida será 747x550
            pi.thumbnail((747, 550), Image.Resampling.LANCZOS)
            # Centramos la imagen horizontalmente en x=126
            img.paste(pi, (126, 236), pi)

            # --- POSICIONAMIENTO DE TEXTOS (LADO IZQUIERDO) ---
            cx = 200 
            anchor_y = 750 # Subimos el inicio de los textos para dar aire abajo

            # Marca: anchor "lt" (Left Top)
            draw.text((cx, anchor_y), row['Marca'], font=f_m, fill=txt_c, anchor="lt")
            
            # Nombre del producto: Máximo 2 filas
            # Reducimos 'width' a 28 para que el texto salte antes de chocar con el precio
            ny = anchor_y + 60 # Espacio suficiente después de la Marca
            lineas_nombre = textwrap.wrap(row['Nombre del producto'], width=28)[:2]
            for l in lineas_nombre:
                draw.text((cx, ny), l, font=f_p, fill=txt_c, anchor="lt")
                ny += 35 # Salto entre líneas de producto
            
            # --- POSICIONAMIENTO DE PRECIO Y SKU (LADO DERECHO - NIVELADO) ---
            # Usamos una altura fija nivelada con el bloque de texto (anchor_y + margen)
            punto_precio_y = anchor_y + 80 
            
            p_v = str(row['Precio desc'])
            # Reducimos la separación entre S/ y el monto a 40px para que se vea más unido
            tw = draw.textlength("S/", font=f_ps) + draw.textlength(p_v, font=f_pv) + 40
            px = 820 - tw//2 # Ajustamos el centro del precio un poco más a la derecha
            
            # Dibujamos el precio centrado en su propia columna
            draw.text((px, punto_precio_y), "S/", font=f_ps, fill=txt_c, anchor="mm")
            draw.text((px + draw.textlength("S/", font=f_ps) + 40, punto_precio_y), p_v, font=f_pv, fill=txt_c, anchor="mm")
            
            # SKU centrado debajo del precio
            draw.text((820, punto_precio_y + 70), str(row['SKU']), font=f_s_ind, fill=txt_c, anchor="mm") 

            # --- CONFIGURACIÓN DE LEGALES (SE MANTIENE IGUAL) ---
            f_l_bold = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 13)
            tit_legal = "CONDICIONES GENERALES: "
            cuerpo_legal = str(row['Legales'])
            
            ancho_negrita = draw.textlength(tit_legal, font=f_l_bold)
            draw.text((50, 990), tit_legal, font=f_l_bold, fill=txt_c)

            draw_justified_text(
                draw, cuerpo_legal, f_l, 
                y_start=990, x_start=50, x_end=1030, 
                fill=txt_c, line_spacing=2, prefix_width=ancho_negrita
            )

    # Guardar y retornar URL
    fname = f"{row['SKU'] or row['ID_Flyer']}_{formato}_{color_version}.jpg"
    img.save(f"output/{fname}", quality=95); return f"{RAW_URL}{fname}"

# --- BUCLE DE EJECUCIÓN PRINCIPAL ---
data, res_sheet, viejos = get_sheets_data(); os.makedirs('output', exist_ok=True)
h_lima = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")

# Procesar productos individuales (Story, PPL, Display)
for idx, row in data.iterrows():
    f_v = str(row['Formato']).upper().strip()
    if f_v in ["FLYER", "", "0"]: continue
    for c in (["AMARILLO", "AZUL"] if str(row['Tipo de diseño']).strip() == "DSCTOS POWER" else ["AMARILLO"]):
        llave = f"{row['SKU']}_{f_v}_{c}".upper()
        if llave not in viejos:
            url = generar_diseno(row, c)
            if url: res_sheet.append_row([h_lima, llave, row['Tipo de diseño'], f_v, c, url])

# Procesar Flyers (Agrupados por ID_Flyer)
fly_g = data[data['Formato'].astype(str).str.upper().str.strip() == "FLYER"]
for id_f, group in fly_g.groupby('ID_Flyer'):
    if str(id_f) in ["0", "0.0", ""]: continue
    for c in (["AZUL", "AMARILLO"] if str(group.iloc[0]['Tipo de diseño']).strip() == "DSCTOS POWER" else ["AMARILLO"]):
        llave = f"{id_f}_FLYER_{c}".upper()
        if llave not in viejos:
            url = generar_diseno(group, c)
            if url: res_sheet.append_row([h_lima, llave, group.iloc[0]['Tipo de diseño'], "FLYER", c, url])
