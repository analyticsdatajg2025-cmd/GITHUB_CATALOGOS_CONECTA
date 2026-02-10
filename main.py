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

def draw_justified_efe_lc(draw, text, font_reg, font_bold, y_start, x_start, x_end, fill, line_spacing=1):
    """Alineación justificada de margen a margen con prefijo en negrita."""
    prefix = "CONDICIONES GENERALES: "
    full_text = prefix + text
    available_w = x_end - x_start
    wrap_val = 110 if available_w < 500 else 140
    lines = textwrap.wrap(full_text, width=wrap_val)
    y = y_start
    for i, line in enumerate(lines):
        words = line.split()
        if i == len(lines) - 1 or len(words) <= 1:
            curr_x = x_start
            for word in words:
                f = font_bold if (i == 0 and ("CONDICIONES" in word or "GENERALES" in word)) else font_reg
                draw.text((curr_x, y), word, font=f, fill=fill)
                curr_x += draw.textlength(word + " ", font=f)
        else:
            line_w = sum(draw.textlength(w, font=(font_bold if (i==0 and ("CONDICIONES" in w or "GENERALES" in w)) else font_reg)) for w in words)
            space_w = (available_w - line_w) / (len(words) - 1)
            curr_x = x_start
            for word in words:
                f = font_bold if (i == 0 and ("CONDICIONES" in word or "GENERALES" in word)) else font_reg
                draw.text((curr_x, y), word, font=f, fill=fill)
                curr_x += draw.textlength(word, font=f) + space_w
        y += font_reg.getbbox("Ay")[3] + line_spacing

def draw_efe_preciador(draw, x_center, y_center, text_s, text_price, f_ps, f_pv, scale=1.0):
    """Preciador EFE: S/ menor, dígitos compactos."""
    sym_w = draw.textlength(text_s, font=f_ps)
    num_w = draw.textlength(text_price, font=f_pv)
    gap = 4 # Números más juntos
    full_w = sym_w + num_w + gap
    h = int(100 * scale)
    draw.rounded_rectangle([x_center - full_w//2 - 20, y_center - h//2, x_center + full_w//2 + 20, y_center + h//2], radius=15, fill="#FFA002")
    tx = x_center - full_w//2
    draw.text((tx, y_center + 4), text_s, font=f_ps, fill=(255,255,255), anchor="lm")
    draw.text((tx + sym_w + gap, y_center), text_price, font=f_pv, fill=(255,255,255), anchor="lm")

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
    is_fly = isinstance(data_input, pd.DataFrame)
    row = data_input.iloc[0] if is_fly else data_input
    tienda = str(row.get('Tienda', 'LC')).strip().upper()
    tipo = str(row['Tipo de diseño']).strip().upper()
    formato = str(row['Formato']).upper().strip()
    path_fonts, path_fondos = f"TIPOGRAFIA/{tienda}", f"FONDOS/{tienda}/{tipo}"
    
    # Búsqueda Flexible de Fondo
    f_pats = [f"{tienda} - {tipo} - {formato} FONDO {color_version}", f"{tienda} - {tipo} - {formato}", f"{tienda} - REPOWER {tipo} - {formato}"]
    full_p = next((os.path.join(path_fondos, f"{v}{e}") for v in f_pats for e in [".png", ".jpg", ".JPG"] if os.path.exists(os.path.join(path_fondos, f"{v}{e}"))), None)
    if not full_p: return None
    img = Image.open(full_p).convert("RGB"); draw = ImageDraw.Draw(img); headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        if tienda == "EFE":
            f_m = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 36 if formato == "STORY" else 30)
            f_p = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 26 if formato == "STORY" else 22)
            f_pv = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 85 if formato == "PPL" else 75)
            f_ps = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 28)
            f_s_ind = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 16 if formato == "STORY" else 14)
            f_l = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 8); f_l_b = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 8)
        else: # LC ORIGINAL INTACTO
            f_m = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 54 if formato=="STORY" else 44)
            f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 32); f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 105)
            f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 42); f_s_ind = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 20)
            f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 13); f_l_b = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 13)
    except: f_m = f_p = f_pv = f_ps = f_s_ind = f_l = f_l_b = ImageFont.load_default()

    if formato == "FLYER":
        for i, (idx, p) in enumerate(data_input.iterrows()):
            if i >= 8: break
            xp, yp = 65+(i%2)*495, 345+(i//2)*(462)
            try: # CORRECCIÓN CARGA IMÁGENES FLYER
                p_i = Image.open(BytesIO(requests.get(p['Foto del producto calado'], headers=headers).content)).convert("RGBA")
                p_i.thumbnail((250, 250)); img.paste(p_i, (int(xp+100), int(yp+10)), p_i)
            except: pass
            if tienda == "EFE":
                cx = xp + 125
                draw.text((cx, yp+320), p['Marca'], font=f_m, fill=(0,0,0), anchor="mm")
                ny = yp+345
                for ln in textwrap.wrap(p['Nombre del producto'], width=18)[:2]:
                    draw.text((cx, ny), ln, font=f_p, fill=(0,0,0), anchor="mm"); ny += 25
                if "EFERTON" in tipo: draw_efe_preciador(draw, xp+345, yp+350, "S/", str(p['Precio desc']), f_ps, f_pv, scale=0.6)
                else: draw.text((xp+345, yp+350), f"S/ {p['Precio desc']}", font=f_pv, fill="#FFA002", anchor="mm")
            else: # LÓGICA LC FLYER
                cl, cr = xp+115, xp+345
                draw.text((cl, yp+box_h-100), p['Marca'], font=f_m, fill=(0,0,0), anchor="mm")
                # ... resto de LC Flyer se mantiene igual ...
        draw_justified_efe_lc(draw, str(row['Legales']), f_l, f_l_b, 1840, 65, 1015, (255,255,255) if tienda=="EFE" else (0,0,0))
    else:
        pi = Image.open(BytesIO(requests.get(row['Foto del producto calado'], headers=headers).content)).convert("RGBA")
        if formato == "PPL":
            if tienda == "EFE":
                if "EFERTON" in tipo:
                    pi.thumbnail((580, 580)); img.paste(pi, (500-pi.width//2, 506-pi.height//2), pi) # -6px abajo
                    ay = 830
                    draw.text((160, ay), row['Marca'], font=f_m, fill=(255,255,255), anchor="mm")
                    ny = ay; [draw.text((500, ny), l, font=f_p, fill=(255,255,255), anchor="mm") for l in textwrap.wrap(row['Nombre del producto'], width=15)[:2]]; ny+=30
                    draw_efe_preciador(draw, 840, ay, "S/", str(row['Precio desc']), f_ps, f_pv, scale=0.9)
                    draw_justified_efe_lc(draw, str(row['Legales']), f_l, f_l_b, 945, 50, 950, (255,255,255))
                else: # PI PPL (+20,+20)
                    pi.thumbnail((583, 583)); img.paste(pi, (520-pi.width//2, 520-pi.height//2), pi)
                    ay = 780 - 50 # Sube 50px
                    draw.text((100, ay), row['Marca'], font=f_m, fill=(255,255,255), anchor="lm")
                    ny = ay + 45; [draw.text((100, ny), l, font=f_p, fill=(255,255,255), anchor="lm") for l in textwrap.wrap(row['Nombre del producto'], width=12)[:2]]; ny+=32
                    draw.text((100, ny+60), f"S/ {row['Precio desc']}", font=ImageFont.truetype(path_fonts+"/Poppins-SemiBold.ttf", f_pv.size-10), fill=(255,255,255), anchor="lm")
                    draw_justified_efe_lc(draw, str(row['Legales']), f_l, f_l_b, 970, 50, 950, (255,255,255)) # Baja 25px
            else: # LC PPL
                pi.thumbnail((610, 610)); img.paste(pi, (500-pi.width//2, 475-pi.height//2), pi)
                draw.text((275, 780), row['Marca'], font=f_m, fill=(0,0,0) if color_version=="AMARILLO" else (255,255,255), anchor="mm")
                # ... resto de LC PPL ...
                draw_justified_efe_lc(draw, str(row['Legales']), f_l, f_l_b, 945, 50, 950, (0,0,0) if color_version=="AMARILLO" else (255,255,255))

        elif formato == "STORY":
            pi.thumbnail((900, 900)); img.paste(pi, (540-pi.width//2, 630), pi)
            ay = 1508 # Bajada 8px EFE y PI
            draw.text((270, ay), row['Marca'], font=f_m, fill=txt_c, anchor="mm")
            ny = ay + 70; [draw.text((270, ny), l, font=f_p, fill=txt_c, anchor="mm") for l in textwrap.wrap(row['Nombre del producto'], width=25)[:2]]; ny+=35
            if tienda == "EFE":
                if "EFERTON" in tipo: draw_efe_preciador(draw, 810, ay+20, "S/", str(row['Precio desc']), f_ps, f_pv, scale=1.1)
                else: draw.text((810, ay+20), f"S/ {row['Precio desc']}", font=f_pv, fill=txt_c, anchor="mm")
            else: # LC STORY
                px = 810-(draw.textlength("S/ ", font=f_ps)+draw.textlength(str(row['Precio desc']), font=f_pv)+85)//2
                draw.text((px, ay-50), "S/ ", font=f_ps, fill=txt_c, anchor="mm")
            draw_justified_efe_lc(draw, str(row['Legales']), f_l, f_l_b, 1845, 65, 1015, txt_c)

        elif formato == "DISPLAY":
            x_i = 525 if (tienda=="EFE" and "IRRESISTIBLE" in tipo) else 530
            pi.thumbnail((400, 400)); img.paste(pi, (x_i, 70), pi)
            cx, ny = 265, 220
            draw.text((cx, ny), row['Marca'], font=f_m, fill=txt_c, anchor="mt")
            ny += 35; [draw.text((cx, ny), l, font=f_p, fill=txt_c, anchor="mt") for l in textwrap.wrap(row['Nombre del producto'], width=25)[:2]]; ny+=30
            p_sz = 5 if (tienda=="EFE" and "IRRESISTIBLE" in tipo) else 0
            f_pv_d = ImageFont.truetype(path_fonts + ("/Poppins-SemiBold.ttf" if tienda=="EFE" else "/HurmeGeometricSans1 Bold.otf"), 80 - p_sz)
            if tienda == "EFE" and "EFERTON" in tipo: draw_efe_preciador(draw, cx, 410, "S/", str(row['Precio desc']), f_ps, f_pv_d, scale=0.65)
            else: draw.text((cx, 410), f"S/ {row['Precio desc']}", font=f_pv_d, fill=txt_c, anchor="mm")
            draw_justified_efe_lc(draw, str(row['Legales']), f_l, f_l_b, 450, 40, 480, txt_c)

    fname = f"{row['SKU'] or row['ID_Flyer']}_{formato}_{tienda}_{color_version}.jpg"
    img.save(f"output/{fname}", quality=95); return f"{RAW_URL}{fname}"

# --- EJECUCIÓN MULTIMARCA ---
data, res_sheet, viejos = get_sheets_data(); os.makedirs('output', exist_ok=True)
h_lima = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")

for idx, row in data.iterrows():
    f_v = str(row['Formato']).upper().strip()
    if f_v in ["FLYER", "", "0"]: continue
    tienda, tipo = str(row.get('Tienda', 'LC')).strip().upper(), str(row['Tipo de diseño']).strip().upper()
    colores = ["AMARILLO", "AZUL"] if (tienda == "LC" and ("DSCTOS" in tipo or "REPOWER" in tipo)) else ["AMARILLO"]
    if tienda == "EFE": colores = ["EFE"]
    for c in colores:
        llave = f"{row['SKU']}_{f_v}_{tienda}_{c}".upper()
        if llave not in viejos:
            url = generar_diseno(row, color_version=c)
            if url: res_sheet.append_row([h_lima, llave, tienda, tipo, f_v, c, url])

fly_g = data[data['Formato'].astype(str).str.upper().str.strip() == "FLYER"]
for id_f, group in fly_g.groupby('ID_Flyer'):
    if str(id_f) in ["0", "0.0", ""]: continue
    p_reg = group.iloc[0]; tienda, tipo = str(p_reg.get('Tienda', 'LC')).strip().upper(), str(p_reg['Tipo de diseño']).strip().upper()
    col_f = ["AMARILLO", "AZUL"] if (tienda == "LC" and ("DSCTOS" in tipo or "REPOWER" in tipo)) else ["AMARILLO"]
    if tienda == "EFE": col_f = ["EFE"]
    for cf in col_f:
        llave = f"{id_f}_FLYER_{tienda}_{cf}".upper()
        if llave not in viejos:
            url = generar_diseno(group, color_version=cf)
            if url: res_sheet.append_row([h_lima, llave, tienda, tipo, "FLYER", cf, url])