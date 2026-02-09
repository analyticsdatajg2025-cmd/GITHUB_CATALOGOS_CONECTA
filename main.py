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

def draw_justified_text(draw, text, font, y_start, x_start, x_end, fill, line_spacing=2):
    """Dibuja texto legal compacto con interlineado de 2px (Global LC/EFE)."""
    available_w = x_end - x_start
    wrap_width = 145 if available_w > 900 else 110
    lines = textwrap.wrap(text, width=wrap_width)
    y = y_start
    for i, line in enumerate(lines):
        words = line.split()
        if i == len(lines) - 1 or len(words) <= 1:
            draw.text((x_start, y), line, font=font, fill=fill)
        else:
            total_w = sum(draw.textlength(w, font=font) for w in words)
            space_width = (available_w - total_w) / (len(words) - 1)
            curr_x = x_start
            for word in words:
                draw.text((curr_x, y), word, font=font, fill=fill)
                curr_x += draw.textlength(word, font=font) + space_width
        y += font.getbbox("Ay")[3] + line_spacing

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

def draw_efe_preciador(draw, x_center, y_center, text_s, text_price, f_ps, f_pv, scale=1.0):
    """Preciador Inteligente Dinámico: Soporta de 2 a 6 cifras sin errores."""
    sym_w = draw.textlength(text_s, font=f_ps)
    num_w = draw.textlength(text_price, font=f_pv)
    gap = 15
    full_w = sym_w + num_w + gap
    h = int(115 * scale)
    # Fondo dinámico según ancho total medido
    draw.rounded_rectangle([x_center - full_w//2 - 25, y_center - h//2, x_center + full_w//2 + 25, y_center + h//2], radius=18, fill="#FFA002")
    # Posicionamiento exacto S/ y Monto
    tx = x_center - full_w//2
    draw.text((tx, y_center), text_s, font=f_ps, fill=(255,255,255), anchor="lm")
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
    is_flyer = isinstance(data_input, pd.DataFrame)
    row = data_input.iloc[0] if is_flyer else data_input
    tienda = str(row.get('Tienda', 'LC')).strip().upper()
    tipo = str(row['Tipo de diseño']).strip().upper()
    formato = str(row['Formato']).upper().strip()
    path_fonts, path_fondos = f"TIPOGRAFIA/{tienda}", f"FONDOS/{tienda}/{tipo}"
    txt_c = (255,255,255) if tienda == "EFE" else ((0,0,0) if color_version == "AMARILLO" else (255,255,255))

    # Búsqueda de Fondos Multi-patrón (Busca con/sin REPOWER)
    f_pats = [f"{tienda} - {tipo} - {formato}", f"{tienda} - REPOWER {tipo} - {formato}", f"{tipo} - {formato}"]
    full_p = next((os.path.join(path_fondos, f"{v}{e}") for v in f_pats for e in [".jpg", ".JPG", ".png", ".PNG"] if os.path.exists(os.path.join(path_fondos, f"{v}{e}"))), None)
    if not full_p: return None
    img = Image.open(full_p).convert("RGB"); draw = ImageDraw.Draw(img)

    try:
        if tienda == "EFE":
            f_m = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 32 if formato == "FLYER" else 42)
            f_p = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 20 if formato == "FLYER" else 28)
            f_pv = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 70 if formato == "FLYER" else 100)
            f_ps = ImageFont.truetype(f"{path_fonts}/Poppins-SemiBold.ttf", 30 if formato == "FLYER" else 40)
            f_s_ind = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 16)
            f_l = ImageFont.truetype(f"{path_fonts}/Poppins-Regular.ttf", 10)
            f_f = ImageFont.truetype(f"{path_fonts}/Poppins-Medium.ttf", 26)
        else: # LA CURACAO
            if formato == "STORY":
                f_m = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 54); f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 32)
                f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 105); f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 42)
                f_s_ind = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 20); f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 14)
            elif formato == "PPL":
                f_m = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 44); f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 24)
                f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 85); f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 36)
                f_s_ind = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 14); f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 13)
            else:
                f_m = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 35); f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 18)
                f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 75); f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 30)
                f_s_ind = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 11); f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 9)
            f_f = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 24)
    except: f_m = f_p = f_pv = f_ps = f_s_ind = f_l = f_f = ImageFont.load_default()

    if formato == "FLYER":
        f_txt = str(row['Fecha_disponibilidad_flyer']).upper()
        if tienda == "EFE":
            wf = draw.textlength(f_txt, font=f_f)
            if "EFERTON" in tipo: draw.rounded_rectangle([540-wf//2-50, 230, 540+wf//2+50, 290], radius=12, outline=(255,255,255), width=3)
            draw.text((540, 260), f_txt, font=f_f, fill=(255,255,255), anchor="mm")
        else: # LC
            wf = draw.textlength(f_txt, font=f_f)
            draw.rounded_rectangle([75, 235, 75+wf+35, 285], radius=10, outline=(0,0,0) if color_version=="AMARILLO" else (255,255,255), width=3)
            draw.text((75+(wf+35)//2, 260), f_txt, font=f_f, fill=(0,0,0) if color_version=="AMARILLO" else (255,255,255), anchor="mm")

        box_h = 330 if len(data_input) > 6 else 450
        for i, (idx, p) in enumerate(data_input.iterrows()):
            if i >= 8: break
            xp, yp = 65+(i%2)*495, 345+(i//2)*(box_h+12)
            if tienda == "EFE":
                line_c = "#00ACDE" if "EFERTON" in tipo else "#0A74DA"
                if i % 2 == 0: draw_dotted_line(draw, (xp+475, yp+20), (xp+475, yp+box_h-20), line_c)
                if i < 6: draw_dotted_line(draw, (xp+20, yp+box_h+6), (xp+435, yp+box_h+6), line_c)
            else: draw.rounded_rectangle([xp, yp, xp+455, yp+box_h], radius=15, fill=(255,255,255), outline=(254, 215, 0), width=2)
            
            pi = Image.open(BytesIO(requests.get(p['Foto del producto calado']).content)).convert("RGBA")
            pi.thumbnail((box_h-120, box_h-140)); img.paste(pi, (int(xp+(455-pi.width)//2), int(yp+10)), pi)
            
            if tienda == "EFE":
                cx_l = xp + 120
                draw.text((cx_l, yp+box_h-115), p['Marca'], font=f_m, fill=(0,0,0), anchor="mm")
                ny = yp+box_h-90
                for ln in textwrap.wrap(p['Nombre del producto'], width=12):
                    draw.text((cx_l, ny), ln, font=f_p, fill=(0,0,0), anchor="mm"); ny += 24
                draw.text((cx_l, ny+5), str(p['SKU']), font=f_s_ind, fill=(0,0,0), anchor="mm")
                if "EFERTON" in tipo: draw_efe_preciador(draw, xp+345, yp+box_h-75, "S/", str(p['Precio desc']), f_ps, f_pv, scale=0.65)
                else: draw.text((xp+345, yp+box_h-75), f"S/ {p['Precio desc']}", font=f_pv, fill="#FFA002", anchor="mm")
            else: # LC
                draw.text((xp+115, yp+box_h-100), p['Marca'], font=f_m, fill=(0,0,0), anchor="mm")
                ny = yp+box_h-65
                for ln in textwrap.wrap(p['Nombre del producto'], width=18)[:2]:
                    draw.text((xp+115, ny), ln, font=f_p, fill=(0,0,0), anchor="mm"); ny += 20
                px = (xp+345)-(draw.textlength("S/", font=f_ps)+draw.textlength(str(p['Precio desc']), font=f_pv)+12)//2
                draw.text((px, yp+box_h-75), "S/", font=f_ps, fill=(0,0,0), anchor="lm")
                draw.text((px+draw.textlength("S/", font=f_ps)+12, yp+box_h-75), str(p['Precio desc']), font=f_pv, fill=(0,0,0), anchor="lm")
                draw.text((xp+345, yp+box_h-20), str(p['SKU']), font=f_s_fly, fill=(110,110,110), anchor="mm")
        draw_justified_text(draw, "CONDICIONES GENERALES: "+str(row['Legales']), f_l, 1835, 65, 1015, (255,255,255) if tienda=="EFE" else txt_c)

    else:
        pi = Image.open(BytesIO(requests.get(row['Foto del producto calado']).content)).convert("RGBA")
        if formato == "PPL":
            if tienda == "EFE":
                pi.thumbnail((580, 580)); img.paste(pi, (500-pi.width//2, 500-pi.height//2), pi)
                ay = 830
                if "EFERTON" in tipo:
                    draw.text((160, ay), row['Marca'], font=f_m, fill=(255,255,255), anchor="mm")
                    ny = ay - 15
                    for l in textwrap.wrap(row['Nombre del producto'], width=15):
                        draw.text((500, ny), l, font=f_p, fill=(255,255,255), anchor="mm"); ny += 32
                    draw.text((500, ny+5), str(row['SKU']), font=f_s_ind, fill=(255,255,255), anchor="mm")
                    draw_efe_preciador(draw, 840, ay, "S/", str(row['Precio desc']), f_ps, f_pv, scale=0.9)
                else: # IRRESISTIBLE EFE
                    draw.text((100, 800), row['Marca'], font=f_m, fill=(255,255,255), anchor="lm")
                    draw.text((100, 845), row['Nombre del producto'], font=f_p, fill=(255,255,255), anchor="lm")
                    draw.text((100, 885), str(row['SKU']), font=f_s_ind, fill=(255,255,255), anchor="lm")
                    draw.text((100, 940), f"S/ {row['Precio desc']}", font=f_pv, fill=(255,255,255), anchor="lm")
            else: # LC PPL
                pi.thumbnail((610, 610)); img.paste(pi, (500-pi.width//2, 475-pi.height//2), pi)
                draw.text((275, 780), row['Marca'], font=f_m, fill=txt_c, anchor="mm")
                ny = 780+55
                for l in textwrap.wrap(row['Nombre del producto'], width=22):
                    draw.text((275, ny), l, font=f_p, fill=txt_c, anchor="mm"); ny += 34
                px = 735-(draw.textlength("S/ ", font=f_ps)+draw.textlength(str(row['Precio desc']), font=f_pv)+80)//2
                draw.text((px, 780), "S/ ", font=f_ps, fill=txt_c, anchor="mm")
                draw.text((px+draw.textlength("S/ ", font=f_ps)+80, 780), str(row['Precio desc']), font=f_pv, fill=txt_c, anchor="mm")
                draw.text((735, 780+60), str(row['SKU']), font=f_s_ind, fill=txt_c, anchor="mm")
            draw_justified_text(draw, "CONDICIONES GENERALES: "+str(row['Legales']), f_l, 945, 50, 950, (255,255,255) if tienda=="EFE" else txt_c)

        elif formato == "STORY":
            pi.thumbnail((900, 900)); img.paste(pi, (540-pi.width//2, 620), pi)
            ay = 1480
            if tienda == "EFE":
                draw.text((270, ay), row['Marca'], font=f_m, fill=(255,255,255), anchor="mm")
                ny = ay + 70
                for l in textwrap.wrap(row['Nombre del producto'], width=16):
                    draw.text((270, ny), l, font=f_p, fill=(255,255,255), anchor="mm"); ny += 40
                draw.text((270, ny+5), str(row['SKU']), font=f_s_ind, fill=(255,255,255), anchor="mm")
                if "EFERTON" in tipo: draw_efe_preciador(draw, 810, ay+15, "S/", str(row['Precio desc']), f_ps, f_pv, scale=1.1)
                else: draw.text((810, ay+15), f"S/ {row['Precio desc']}", font=f_pv, fill=(255,255,255), anchor="mm")
            else: # LC STORY
                draw.text((270, ay-50), row['Marca'], font=f_m, fill=txt_c, anchor="mm")
                ny = ay + 15
                for l in textwrap.wrap(row['Nombre del producto'], width=20):
                    draw.text((270, ny), l, font=f_p, fill=txt_c, anchor="mm"); ny += 42
                px = 810-(draw.textlength("S/ ", font=f_ps)+draw.textlength(str(row['Precio desc']), font=f_pv)+85)//2
                draw.text((px, ay-50), "S/ ", font=f_ps, fill=txt_c, anchor="mm")
                draw.text((px+draw.textlength("S/ ", font=f_ps)+85, ay-50), str(row['Precio desc']), font=f_pv, fill=txt_c, anchor="mm")
                draw.text((810, ay+30), str(row['SKU']), font=f_s_ind, fill=txt_c, anchor="mm")
            draw_justified_text(draw, "CONDICIONES GENERALES: "+str(row['Legales']), f_l, 1835, 65, 1015, (255,255,255) if tienda=="EFE" else txt_c)

        elif formato == "DISPLAY":
            pi.thumbnail((400, 400)); img.paste(pi, (530, 70), pi); cx = 265
            if tienda == "EFE":
                draw.text((cx, 220), row['Marca'], font=f_m, fill=(255,255,255), anchor="mt")
                ny = 265
                for l in textwrap.wrap(row['Nombre del producto'], width=20):
                    draw.text((cx, ny), l, font=f_p, fill=(255,255,255), anchor="mt"); ny += 32
                draw.text((cx, ny+5), str(row['SKU']), font=f_s_ind, fill=(255,255,255), anchor="mt")
                if "EFERTON" in tipo: draw_efe_preciador(draw, cx, 410, "S/", str(row['Precio desc']), f_ps, f_pv, scale=0.7)
                else: draw.text((cx, 410), f"S/ {row['Precio desc']}", font=f_pv, fill=(255,255,255), anchor="mm")
            else: # LC DISPLAY
                draw.text((cx, 185), row['Marca'], font=f_m, fill=txt_c, anchor="mt")
                ny = 235
                for l in textwrap.wrap(row['Nombre del producto'], width=22):
                    draw.text((cx, ny), l, font=f_p, fill=txt_c, anchor="mt"); ny += 25
                px = cx-(draw.textlength("S/ ", font=f_ps)+draw.textlength(str(row['Precio desc']), font=f_pv)+15)//2
                draw.text((px, ny+45), "S/ ", font=f_ps, fill=txt_c, anchor="lm")
                draw.text((px+draw.textlength("S/ ", font=f_ps)+15, ny+45), str(row['Precio desc']), font=f_pv, fill=txt_c, anchor="lm")
                draw.text((cx, ny+90), str(row['SKU']), font=f_s_ind, fill=txt_c, anchor="mt")
            leg_txt = textwrap.fill("CONDICIONES GENERALES: "+str(row['Legales']), width=115)
            draw.multiline_text((40, 450), leg_txt, font=f_l, fill=(255,255,255) if tienda=="EFE" else txt_c, spacing=3)

    fname = f"{row['SKU'] or row['ID_Flyer']}_{formato}_{tienda}.jpg"
    img.save(f"output/{fname}", quality=95); return f"{RAW_URL}{fname}"

# --- EJECUCIÓN 7 COLUMNAS ---
data, res_sheet, viejos = get_sheets_data(); os.makedirs('output', exist_ok=True)
h_lima = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")

for idx, row in data.iterrows():
    f_v = str(row['Formato']).upper().strip()
    if f_v in ["FLYER", "", "0"]: continue
    tienda = str(row.get('Tienda', 'LC')).strip().upper()
    tipo = str(row['Tipo de diseño']).strip().upper()
    colores = ["AMARILLO", "AZUL"] if (tienda == "LC" and "DSCTOS" in tipo) else ["AMARILLO"]
    if tienda == "EFE": colores = ["EFE"]
    for c in colores:
        llave = f"{row['SKU']}_{f_v}_{tienda}_{c}".upper()
        if llave not in viejos:
            url = generar_diseno(row, color_version=c)
            if url: res_sheet.append_row([h_lima, llave, tienda, tipo, f_v, c, url])

fly_g = data[data['Formato'].astype(str).str.upper().str.strip() == "FLYER"]
for id_f, group in fly_g.groupby('ID_Flyer'):
    if str(id_f) in ["0", "0.0", ""]: continue
    p_reg = group.iloc[0]; tienda = str(p_reg.get('Tienda', 'LC')).strip().upper(); tipo = str(p_reg['Tipo de diseño']).strip().upper()
    colores_f = ["AMARILLO", "AZUL"] if (tienda == "LC" and "DSCTOS" in tipo) else ["AMARILLO"]
    if tienda == "EFE": colores_f = ["EFE"]
    for cf in colores_f:
        llave = f"{id_f}_FLYER_{tienda}_{cf}".upper()
        if llave not in viejos:
            url = generar_diseno(group, color_version=cf)
            if url: res_sheet.append_row([h_lima, llave, tienda, tipo, "FLYER", cf, url])