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

def draw_justified_text(draw, text, font, y_start, x_start, x_end, fill, line_spacing=5):
    available_w = x_end - x_start
    wrap_width = 135 if available_w > 900 else 115
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
    tipo, formato = str(row['Tipo de diseño']).strip(), str(row['Formato']).upper().strip()
    path_fonts, path_fondos = "TIPOGRAFIA/LC", f"FONDOS/LC/{tipo}"
    txt_c = (0,0,0) if color_version == "AMARILLO" else (255,255,255)
    border_c = (254, 215, 0) if color_version == "AMARILLO" else (10, 6, 60)
    accent_date = (0,0,0) if color_version == "AMARILLO" else (255,255,255)

    fname_base = f"LC - {tipo} - {'FLYER' if formato == 'FLYER' else formato}"
    full_p = next((os.path.join(path_fondos, f"{v}{e}") for v in [f"{fname_base} FONDO {color_version}", f"{fname_base} {color_version}", fname_base] for e in [".png", ".jpg", ".PNG", ".JPG"] if os.path.exists(os.path.join(path_fondos, f"{v}{e}"))), None)
    if not full_p: return None
    img = Image.open(full_p).convert("RGB"); draw = ImageDraw.Draw(img)

    try:
        if formato == "STORY":
            f_m = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 54)
            f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 32)
            f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 105)
            f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 42)
            f_s_ind = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 20) # SKU Reducido
            f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 14)
        elif formato == "PPL":
            f_m = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 44)
            f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 24)
            f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 85)
            f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 36)
            f_s_ind = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 14) # SKU Reducido
            f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 13)
        else: # DISPLAY
            f_m = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 35); f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 18)
            f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 75); f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 30)
            f_s_ind = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 11); f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 9)
        
        f_s_fly = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 11); f_f = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 24)
    except: f_m = f_p = f_pv = f_ps = f_s_ind = f_s_fly = f_f = f_l = ImageFont.load_default()

    if formato == "FLYER":
        f_txt = str(row['Fecha_disponibilidad_flyer']).upper()
        wf = draw.textlength(f_txt, font=f_f)
        draw.rounded_rectangle([75, 235, 75+wf+35, 285], radius=10, outline=accent_date, width=3)
        draw.text((75+(wf+35)//2, 260), f_txt, font=f_f, fill=accent_date, anchor="mm")
        box_h = 330 if len(data_input) > 6 else 450
        for i, (idx, p) in enumerate(data_input.iterrows()):
            if i >= 8: break
            xp, yp = 65+(i%2)*495, 345+(i//2)*(box_h+12)
            draw.rounded_rectangle([xp, yp, xp+455, yp+box_h], radius=15, fill=(255,255,255), outline=border_c, width=2)
            pi = Image.open(BytesIO(requests.get(p['Foto del producto calado']).content)).convert("RGBA")
            pi.thumbnail((box_h-90, box_h-110)); img.paste(pi, (int(xp+(455-pi.width)//2), int(yp+10)), pi)
            cl, cr = xp+115, xp+345
            f_m_fly = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 26 if len(p['Marca']) < 12 else 18)
            draw.text((cl, yp+box_h-100), p['Marca'], font=f_m_fly, fill=(0,0,0), anchor="mm")
            ny = yp+box_h-65
            for ln in textwrap.wrap(p['Nombre del producto'], width=18)[:2]:
                draw.text((cl, ny), ln, font=f_p, fill=(0,0,0), anchor="mm"); ny += 20
            px = cr - (draw.textlength("S/", font=f_ps) + draw.textlength(str(p['Precio desc']), font=f_pv) + 12)//2
            draw.text((px, yp+box_h-75), "S/", font=f_ps, fill=(0,0,0), anchor="lm")
            draw.text((px + draw.textlength("S/", font=f_ps) + 12, yp+box_h-75), str(p['Precio desc']), font=f_pv, fill=(0,0,0), anchor="lm")
            draw.text((cr, yp+box_h-20), str(p['SKU']), font=f_s_fly, fill=(110,110,110), anchor="mm")
        draw_justified_text(draw, "CONDICIONES GENERALES: "+str(row['Legales']), f_l, 1840, 65, 1015, txt_c)

    else:
        pi = Image.open(BytesIO(requests.get(row['Foto del producto calado']).content)).convert("RGBA")
        if formato == "DISPLAY":
            pi.thumbnail((440, 440)); img.paste(pi, (530, 45), pi); cx, ny = 265, 235
            draw.text((cx, 185), row['Marca'], font=f_m, fill=txt_c, anchor="mt")
            for l in textwrap.wrap(row['Nombre del producto'], width=22):
                draw.text((cx, ny), l, font=f_p, fill=txt_c, anchor="mt"); ny += 25
            tw = draw.textlength("S/ ", font=f_ps) + draw.textlength(str(row['Precio desc']), font=f_pv) + 15
            px = cx - tw//2
            draw.text((px, ny+45), "S/ ", font=f_ps, fill=txt_c, anchor="lm")
            draw.text((px+draw.textlength("S/ ", font=f_ps)+15, ny+45), str(row['Precio desc']), font=f_pv, fill=txt_c, anchor="lm")
            draw.text((cx, ny+90), str(row['SKU']), font=f_s_ind, fill=txt_c, anchor="mt")
            leg_txt = textwrap.fill("CONDICIONES GENERALES: " + str(row['Legales']), width=115)
            draw.multiline_text((40, 455), leg_txt, font=f_l, fill=txt_c, spacing=7)
        
        elif formato == "STORY":
            pi.thumbnail((900, 900)); img.paste(pi, (540-pi.width//2, 530), pi)
            anchor_y = 1430 # Nivelado Marca/Precio
            draw.text((270, anchor_y), row['Marca'], font=f_m, fill=txt_c, anchor="mm")
            ny = anchor_y + 65
            for l in textwrap.wrap(row['Nombre del producto'], width=20):
                draw.text((270, ny), l, font=f_p, fill=txt_c, anchor="mm"); ny += 42
            p_v = str(row['Precio desc'])
            tw = draw.textlength("S/ ", font=f_ps) + draw.textlength(p_v, font=f_pv) + 85
            px = 810 - tw//2
            draw.text((px, anchor_y), "S/ ", font=f_ps, fill=txt_c, anchor="mm")
            draw.text((px + draw.textlength("S/ ", font=f_ps) + 85, anchor_y), p_v, font=f_pv, fill=txt_c, anchor="mm")
            # SKU STORY: Más pequeño y pegado al precio
            draw.text((810, anchor_y + 65), str(row['SKU']), font=f_s_ind, fill=txt_c, anchor="mm") 
            draw_justified_text(draw, "CONDICIONES GENERALES: "+str(row['Legales']), f_l, 1845, 65, 1015, txt_c)

        elif formato == "PPL":
            # --- AJUSTE PPL: Bajado y Agrandado ---
            pi.thumbnail((630, 630)); img.paste(pi, (500-pi.width//2, 465-pi.height//2), pi)
            anchor_y = 780 # Nivelado Marca/Precio
            draw.text((275, anchor_y), row['Marca'], font=f_m, fill=txt_c, anchor="mm")
            ny = anchor_y + 55
            for l in textwrap.wrap(row['Nombre del producto'], width=22):
                draw.text((275, ny), l, font=f_p, fill=txt_c, anchor="mm"); ny += 34
            p_v = str(row['Precio desc'])
            tw = draw.textlength("S/ ", font=f_ps) + draw.textlength(p_v, font=f_pv) + 80
            px = 735 - tw//2
            draw.text((px, anchor_y), "S/ ", font=f_ps, fill=txt_c, anchor="mm")
            draw.text((px + draw.textlength("S/ ", font=f_ps) + 80, anchor_y), p_v, font=f_pv, fill=txt_c, anchor="mm")
            # SKU PPL: Reducido y pegado al precio
            draw.text((735, anchor_y + 60), str(row['SKU']), font=f_s_ind, fill=txt_c, anchor="mm") 
            draw_justified_text(draw, "CONDICIONES GENERALES: "+str(row['Legales']), f_l, 950, 50, 950, txt_c)

    fname = f"{row['SKU'] or row['ID_Flyer']}_{formato}_{color_version}.jpg"
    img.save(f"output/{fname}", quality=95); return f"{RAW_URL}{fname}"

# --- EJECUCIÓN ---
data, res_sheet, viejos = get_sheets_data(); os.makedirs('output', exist_ok=True)
h_lima = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")
for idx, row in data.iterrows():
    f_v = str(row['Formato']).upper().strip()
    if f_v in ["FLYER", "", "0"]: continue
    for c in (["AMARILLO", "AZUL"] if str(row['Tipo de diseño']).strip() == "DSCTOS POWER" else ["AMARILLO"]):
        llave = f"{row['SKU']}_{f_v}_{c}".upper()
        if llave not in viejos:
            url = generar_diseno(row, c)
            if url: res_sheet.append_row([h_lima, llave, row['Tipo de diseño'], f_v, c, url])
fly_g = data[data['Formato'].astype(str).str.upper().str.strip() == "FLYER"]
for id_f, group in fly_g.groupby('ID_Flyer'):
    if str(id_f) in ["0", "0.0", ""]: continue
    for c in (["AZUL", "AMARILLO"] if str(group.iloc[0]['Tipo de diseño']).strip() == "DSCTOS POWER" else ["AMARILLO"]):
        llave = f"{id_f}_FLYER_{c}".upper()
        if llave not in viejos:
            url = generar_diseno(group, c)
            if url: res_sheet.append_row([h_lima, llave, group.iloc[0]['Tipo de diseño'], "FLYER", c, url])