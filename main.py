import os
import json
import requests
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from datetime import datetime, timedelta
from io import BytesIO
import textwrap

# --- CONFIGURACIÓN DE RUTAS ---
USER_GH = "analyticsdatajg2025-cmd"
REPO_GH = "GITHUB_CATALOGOS_CONECTA"
RAW_URL = f"https://raw.githubusercontent.com/{USER_GH}/{REPO_GH}/main/output/"

# --- AJUSTE: marca que se escribe en la columna C de 'Resultados' ---
# Antes no se enviaba y habia que ponerla a mano. El append es POSICIONAL,
# asi que el orden debe ser exactamente:
#   A Fecha | B ID | C Tienda | D Diseño | E Formato | F Color | G Link Imagen
TIENDA_SCRIPT = "LC"

# --- FEEDS DE PRODUCTO (columna H 'Link web' de 'Resultados') ---
# El SKU del Sheet se busca contra la columna 'id' del feed y se devuelve su 'link'.
# El feed se descarga UNA sola vez por corrida y queda en cache.
FEEDS = {
    "LC":  "https://www.lacuracao.pe/media/feed/google_curacao.txt",
    "EFE": "https://www.efe.com.pe/media/feed/google_prueba_copy_copy.txt",
}
TEXTO_SIN_FEED = "NO SE ENCUENTRA EN EL FEED"

# Un flyer agrupa varios SKUs y no tiene una sola pagina de producto.
# True  -> usa el link del PRIMER producto del grupo.
# False -> deja TEXTO_SIN_FEED en los flyers.
FLYER_USA_PRIMER_SKU = True

_feed_cache = {}

def cargar_feed(tienda):
    """Descarga el feed de la tienda y devuelve {SKU_MAYUSCULAS: link}. Cachea por corrida."""
    tienda = str(tienda).strip().upper()
    if tienda in _feed_cache:
        return _feed_cache[tienda]

    url = FEEDS.get(tienda)
    mapa = {}
    if not url:
        print(f"⚠️  No hay feed configurado para la tienda '{tienda}'.")
        _feed_cache[tienda] = mapa
        return mapa

    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        try:
            texto = r.content.decode("utf-8")
        except UnicodeDecodeError:
            texto = r.content.decode("latin-1")

        lineas = texto.splitlines()
        if not lineas:
            raise ValueError("el feed vino vacio")

        cab = [c.strip().lower() for c in lineas[0].split("\t")]
        i_id, i_link = cab.index("id"), cab.index("link")

        for ln in lineas[1:]:
            if not ln.strip():
                continue
            campos = ln.split("\t")
            if len(campos) <= max(i_id, i_link):
                continue  # fila truncada: se ignora
            sku_feed = campos[i_id].strip().upper()
            link_feed = campos[i_link].strip()
            if sku_feed and link_feed:
                mapa[sku_feed] = link_feed

        print(f"✅ Feed {tienda}: {len(mapa)} SKUs cargados desde {url}")
    except Exception as e:
        print(f"⚠️  No se pudo leer el feed de {tienda} ({url}): {e}. "
              f"Todos los links web quedaran como '{TEXTO_SIN_FEED}'.")

    _feed_cache[tienda] = mapa
    return mapa

def link_web(tienda, sku):
    """Devuelve el link de redireccion del SKU, o el texto de fallback si no esta en el feed."""
    if sku is None:
        return TEXTO_SIN_FEED
    clave = str(sku).strip().upper()
    if not clave or clave in ("NAN", "NONE"):
        return TEXTO_SIN_FEED
    return cargar_feed(tienda).get(clave, TEXTO_SIN_FEED)

# --- AJUSTES PARA PIEZAS SIN PRECIO (separación entre nombre y SKU) ---
GAP_SKU_SIN_PRECIO = {"DISPLAY": 15, "STORY": 12, "PPL": 6, "FLYER": 2}

# --- AJUSTE: medidas obligatorias por formato ---
# Si el fondo no mide esto, el lienzo real no coincide con las coordenadas del
# código y TODO queda descentrado. Se normaliza antes de pintar y se avisa.
MEDIDAS_FORMATO = {
    "PPL":     (1080, 1080),
    "STORY":   (1080, 1920),
    "FLYER":   (1080, 1920),
    "DISPLAY": (1000,  526),
}

# --- AJUSTE: márgenes de la STORY (texto izquierda / precio derecha, espejados) ---
STORY_MARGEN = 150

# ======================================================================
# AJUSTES POR CAMPAÑA  (mover elementos sin tocar el resto del codigo)
# ======================================================================
# La clave es el "Tipo de diseño" del Sheet, EN MAYUSCULAS.
# Una campaña que NO figure aqui usa el layout de siempre, sin ningun cambio.
#
#   dx  -> mover a la DERECHA   (negativo = izquierda)
#   dy  -> mover hacia ABAJO    (negativo = arriba)
#
# Elementos por formato:
#   PPL / STORY / DISPLAY: img_dx img_dy  txt_dx txt_dy  precio_dx precio_dy  legales_dy
#   FLYER:                 fecha_dy  grid_dy  legales_dy
#
#   img_escala -> factor de tamaño de la foto del producto (1.0 = igual que siempre,
#                 0.85 = 15% mas chica). Solo en PPL/STORY/DISPLAY.
#
# "texto_color" fuerza el color del texto. None = automatico segun el fondo.
AJUSTES_CAMPANA = {
    "DSCTOS POWER": {
        "texto_color": None,
        # Baja la foto, la marca/nombre y el precio. Los legales NO se mueven.
        "PPL": {"img_dy": 30, "txt_dy": 30, "precio_dy": 30},
    },
    "KV COMPUTO LC": {
        "texto_color": None,
        "PPL":     {"img_escala": 0.85, "img_dx": -2, "img_dy": 169, "txt_dx": -105, "txt_dy": 65,
                    "precio_dx": 14, "precio_dy": 82, "legales_dy": 40},
        "DISPLAY": {"img_dx": -70, "img_dy": -1, "txt_dx": -86, "txt_dy": -4,
                    "precio_dx": -79},
        "FLYER":   {"fecha_dy": 65, "grid_dy": 35, "legales_dy": 10},
        # STORY sin calibrar: usa las coordenadas de siempre.
    },
    "DSCTOS POWER": {
        "texto_color": None,
        # Bajan la foto, la marca y el precio. Los legales NO se mueven.
        "PPL":     {"img_dy": 25, "txt_dy": 25, "precio_dy": 25},
    },
    "CYBER WEEK": {
        "texto_color": None,
        # PPL: foto 12% mas chica para que no choque con el logo CYBER WEEK
        "PPL":     {"img_escala": 0.88,
                    "img_dx": 51, "img_dy": 65, "txt_dx": -25, "txt_dy": 76,
                    "precio_dx": -21, "precio_dy": 92, "legales_dy": 45},
        "STORY":   {"precio_dy": 52},
        "DISPLAY": {"txt_dx": -21, "txt_dy": 30, "precio_dx": -23, "precio_dy": 20},
        "FLYER":   {"fecha_dy": 76, "grid_dy": 46, "legales_dy": 14},
    },
}

# ======================================================================
# FORZAR REGENERACION
# ======================================================================
# Normalmente una pieza se salta si ya esta en 'Resultados' Y su archivo existe
# en output/. Cuando cambias las coordenadas de una campaña eso no basta: el
# archivo viejo sigue ahi y la pieza nunca se vuelve a dibujar.
# Pon aqui el "Tipo de diseño" (en MAYUSCULAS) para regenerarlo SIEMPRE.
# Deja el set vacio ( set() ) cuando termines, o cada corrida rehara todo.
FORZAR_REGENERAR = {
    "KV COMPUTO LC",
    "DSCTOS POWER",
}

# ======================================================================
# FOTOS NITIDAS
# ======================================================================
# AJUSTE: las fotos del producto salian borrosas. Dos causas:
#  1) thumbnail() de Pillow por defecto hace una reduccion rapida previa
#     (reducing_gap=2.0) que suaviza la imagen. Aqui se desactiva.
#  2) Al achicar una foto siempre se pierde algo de filo y no se recuperaba.
#     Ahora se aplica un enfoque suave (UnsharpMask) despues de achicar.
NITIDEZ = {"radius": 1.2, "percent": 90, "threshold": 2}

def afilar(im):
    """Enfoque suave que respeta la transparencia del calado."""
    filtro = ImageFilter.UnsharpMask(**NITIDEZ)
    if im.mode == "RGBA":
        alpha = im.getchannel("A")
        rgb = im.convert("RGB").filter(filtro)
        rgb.putalpha(alpha)
        return rgb
    return im.filter(filtro)

def foto_nitida(im, caja):
    """Igual que im.thumbnail(caja) pero sin reduccion rapida y con enfoque."""
    im = im.copy()
    im.thumbnail((max(1, int(caja[0])), max(1, int(caja[1]))), Image.Resampling.LANCZOS, reducing_gap=None)
    return afilar(im)

def normalizar_lienzo(img, formato, ruta_fondo):
    """Fuerza el fondo a la medida oficial del formato. Devuelve la imagen lista."""
    esperado = MEDIDAS_FORMATO.get(formato)
    if esperado and img.size != esperado:
        print(f"⚠️  FONDO FUERA DE MEDIDA: {ruta_fondo} es {img.size}, se esperaba {esperado}. "
              f"Se normaliza (reexportar el fondo es el arreglo correcto).")
        img = img.resize(esperado, Image.Resampling.LANCZOS)
    return img

def tiene_precio(valor):
    """True si la celda 'Precio desc' trae algo válido para pintar."""
    if valor is None:
        return False
    s = str(valor).strip()
    if s == "" or s.lower() in ("nan", "none", "-", "0", "0.0"):
        return False
    try:
        return float(s.replace(",", "")) > 0
    except:
        return True  # texto tipo "GRATIS" o similar: se respeta

def quitar_fondo_blanco(img):
    return img

def draw_justified_text(draw, text, font, y_start, x_start, x_end, fill, line_spacing=5, prefix_width=0):
    available_w = x_end - x_start
    words = text.split()
    lines = []
    current_line = []
    current_w = prefix_width

    for word in words:
        word_w = draw.textlength(word + " ", font=font)
        if current_w + word_w <= available_w:
            current_line.append(word)
            current_w += word_w
        else:
            lines.append(current_line)
            current_line = [word]
            current_w = draw.textlength(word + " ", font=font)
    lines.append(current_line)

    y = y_start
    normal_space_w = draw.textlength(" ", font=font)

    for i, line_words in enumerate(lines):
        if not line_words: continue
        line_x_start = x_start + (prefix_width if i == 0 else 0)
        line_available_w = available_w - (prefix_width if i == 0 else 0)
        line_text = " ".join(line_words)
        total_text_w = sum(draw.textlength(w, font=font) for w in line_words)
        num_spaces = len(line_words) - 1

        if num_spaces > 0:
            target_space_w = (line_available_w - total_text_w) / num_spaces
        else:
            target_space_w = 0

        if i == len(lines) - 1 or len(line_words) <= 1 or target_space_w > (normal_space_w * 2.5):
            draw.text((line_x_start, y), line_text, font=font, fill=fill)
        else:
            curr_x = line_x_start
            for word in line_words:
                draw.text((curr_x, y), word, font=font, fill=fill)
                curr_x += draw.textlength(word, font=font) + target_space_w
        y += font.getbbox("Ay")[3] + line_spacing

def get_sheets_data():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_info = json.loads(os.environ.get('GOOGLE_CREDENTIALS'))
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key("1PmvCyC3d0VvvZSdvWM73NYusrYevVYtRzVs2gbxjw1M")
    data = pd.DataFrame(sheet.worksheet("Hoja 1").get_all_records())
    data.columns = [c.strip() for c in data.columns]

    # FIX: normaliza el nombre de la columna de marca (Tienda o RETAIL), sin importar mayúsculas
    col_map = {c.lower(): c for c in data.columns}
    col_tienda_real = next((col_map[c] for c in ['tienda', 'retail'] if c in col_map), None)
    if col_tienda_real is None:
        raise KeyError(
            "No se encontró una columna de marca ('Tienda' o 'RETAIL') en 'Hoja 1'. "
            f"Columnas detectadas: {list(data.columns)}"
        )
    if col_tienda_real != 'Tienda':
        data = data.rename(columns={col_tienda_real: 'Tienda'})

    res_sheet = sheet.worksheet("Resultados")
    v_act = res_sheet.get_all_values()
    viejos = {r[1].strip().upper() for r in v_act[1:] if len(r) > 1}
    return data, res_sheet, viejos

# ======================================================================
# LAYOUTS  (pega aqui los bloques que copias del Calibrador Conecta)
# ======================================================================
# Ejemplo:
# LAYOUTS = {
#     "CYBER WEEK": {
#         "PPL": {...},
#         "FLYER": {...},
#     },
# }
# Una campaña/formato que NO este aqui se sigue dibujando como siempre
# (coordenadas fijas + AJUSTES_CAMPANA).
LAYOUTS = {
    "CYBER WEEK": {
        "PPL": {
            "foto": {"x": 244, "y": 428, "w": 593, "h": 458, "alinear_h": "centro", "alinear_v": "medio"},
            "marca": {"x": 164, "y": 953, "w": 450, "tam": 43, "fuente": "HurmeGeometricSans1 Bold.otf", "color": "#000000", "interlineado": 48, "max_lineas": 1, "alinear": "izq"},
            "nombre": {"x": 164, "y": 990, "w": 470, "tam": 23, "fuente": "HurmeGeometricSans1 Bold.otf", "color": "#000000", "interlineado": 30, "max_lineas": 2, "alinear": "izq"},
            "sku": {"x": 690, "y": 1001, "w": 200, "tam": 14, "fuente": "HurmeGeometricSans1.otf", "color": "#000000", "interlineado": 17, "alinear": "centro", "max_lineas": 1},
            "precio": {
                "x": 790,
                "y": 968,
                "alinear": "centro",
                "tam_simbolo": 36,
                "tam_numero": 85,
                "fuente": "HurmeGeometricSans1 Bold.otf",
                "separacion": 15,
                "tracking": 0,
                "simbolo_v": "base",
                "color": "#000000",
                "simbolo": "S/",
                "chapa": None,
            },
            "legales": {"x": 50, "y": 1036, "w": 980, "tam": 11, "fuente": "HurmeGeometricSans1.otf", "fuente_negrita": "HurmeGeometricSans1 Bold.otf", "color": "#000000", "interlineado": 14, "justificar": True},
        },
        "FLYER": {
            "fecha": {
                "x": 540,
                "y": 248,
                "h": 50,
                "tam": 24,
                "fuente": "HurmeGeometricSans1 Bold.otf",
                "pad_x": 17,
                "alinear": "centro",
                "relleno": None,
                "borde": "#FFFFFF",
                "borde_w": 3,
                "radio": 10,
                "color": "#FFFFFF",
            },
            "grid": {
                "x": 84,
                "y": 385,
                "celda_w": 436,
                "celda_h": 443,
                "gap_x": 40,
                "gap_y": 30,
                "area_h": 0,
                "centrar_impar": True,
                "estilo": {"fondo": "#FFFFFF", "borde": "#FED700", "borde_w": 2, "radio": 15, "lineas": None},
                "elementos": {"foto": {"x": 59, "y": 20, "w": 338, "h": 338, "alinear_h": "centro", "alinear_v": "arriba"}, "marca": {"x": 14, "y": 377, "w": 200, "tam": 20, "fuente": "HurmeGeometricSans1 Bold.otf", "color": "#0A063C", "interlineado": 24, "alinear": "centro", "max_lineas": 1}, "nombre": {"x": 14, "y": 402, "w": 200, "tam": 18, "fuente": "HurmeGeometricSans1 Bold.otf", "color": "#0A063C", "interlineado": 20, "max_lineas": 2, "alinear": "centro"}, "sku": {"x": 242, "y": 440, "w": 200, "tam": 13, "fuente": "HurmeGeometricSans1.otf", "color": "#0A063C", "interlineado": 16, "alinear": "centro", "max_lineas": 1}, "precio": {
        "x": 342,
        "y": 420,
        "alinear": "centro",
        "tam_simbolo": 24,
        "tam_numero": 60,
        "fuente": "HurmeGeometricSans1 Bold.otf",
        "separacion": 8,
        "tracking": 0,
        "simbolo_v": "base",
        "color": "#0A063C",
        "simbolo": "S/",
        "chapa": None,
    }},
            },
            "grid_8": {
                "x": 64,
                "y": 340,
                "celda_w": 456,
                "celda_h": 375,
                "gap_x": 40,
                "gap_y": 15,
                "area_h": 0,
                "centrar_impar": True,
                "estilo": {"fondo": "#FFFFFF", "borde": "#FED700", "borde_w": 2, "radio": 15, "lineas": None},
                "elementos": {"foto": {"x": 103, "y": 10, "w": 250, "h": 250, "alinear_h": "centro", "alinear_v": "arriba"}, "marca": {"x": 14, "y": 296, "w": 200, "tam": 20, "fuente": "HurmeGeometricSans1 Bold.otf", "color": "#0A063C", "interlineado": 24, "alinear": "centro", "max_lineas": 1}, "nombre": {"x": 14, "y": 321, "w": 200, "tam": 18, "fuente": "HurmeGeometricSans1 Bold.otf", "color": "#0A063C", "interlineado": 20, "max_lineas": 2, "alinear": "centro"}, "sku": {"x": 242, "y": 359, "w": 200, "tam": 13, "fuente": "HurmeGeometricSans1.otf", "color": "#0A063C", "interlineado": 16, "alinear": "centro", "max_lineas": 1}, "precio": {
        "x": 342,
        "y": 339,
        "alinear": "centro",
        "tam_simbolo": 24,
        "tam_numero": 60,
        "fuente": "HurmeGeometricSans1 Bold.otf",
        "separacion": 8,
        "tracking": 0,
        "simbolo_v": "base",
        "color": "#0A063C",
        "simbolo": "S/",
        "chapa": None,
    }},
            },
            "legales": {"x": 64, "y": 1829, "w": 952, "tam": 16, "fuente": "HurmeGeometricSans1.otf", "fuente_negrita": "HurmeGeometricSans1 Bold.otf", "color": "#FFFFFF", "interlineado": 19, "justificar": True},
        },
    },
}

# ======================================================================
# MOTOR DE LAYOUT  (diseños hechos en el Calibrador Conecta)
# ======================================================================
# Si una campaña tiene su formato en LAYOUTS, la pieza se dibuja con este motor
# y NO con las coordenadas de siempre. Si no figura, todo sigue igual que antes.
#
# Este motor y el Calibrador usan las mismas reglas: misma tipografia, el texto
# se ancla en su LINEA BASE (y) y los nombres se cortan por ancho real en pixeles.
# Por eso lo que ves en el Calibrador es lo que sale en la pieza.
#
# Coordenadas en pixeles del lienzo real (PPL 1080x1080, STORY/FLYER 1080x1920,
# DISPLAY 1000x526).
#   foto    : x, y, w, h = caja donde entra la foto (nunca se agranda)
#   textos  : x, w = caja horizontal;  y = linea base de la primera linea
#   precio  : x = borde izq / centro / borde der del bloque segun "alinear"
#   fecha   : x = centro (o borde izq), y = borde superior del recuadro
#   grid    : x, y = esquina de la primera celda; los elementos de la celda
#             van en coordenadas RELATIVAS a la celda
_MOTOR_FUENTES = {}

def _m_fuente(path_fonts, archivo, tam):
    clave = (path_fonts, archivo, int(tam))
    if clave not in _MOTOR_FUENTES:
        try:
            # RAQM = mismo motor de texto que usa el navegador (Calibrador). Si no esta, BASIC.
            try:
                _MOTOR_FUENTES[clave] = ImageFont.truetype(f"{path_fonts}/{archivo}", int(tam),
                                                           layout_engine=ImageFont.Layout.RAQM)
            except Exception:
                _MOTOR_FUENTES[clave] = ImageFont.truetype(f"{path_fonts}/{archivo}", int(tam),
                                                           layout_engine=ImageFont.Layout.BASIC)
        except Exception as e:
            print(f"⚠️  No se pudo cargar la fuente {path_fonts}/{archivo}: {e}")
            _MOTOR_FUENTES[clave] = ImageFont.load_default()
    return _MOTOR_FUENTES[clave]

def _m_color(c, defecto=(255, 255, 255)):
    if not c:
        return defecto
    c = str(c).lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))

def _m_ancho(draw, texto, fuente):
    return draw.textlength(texto, font=fuente)

def _m_lineas(draw, texto, fuente, ancho, max_lineas):
    palabras = str(texto).split()
    lineas, actual = [], []
    for p in palabras:
        prueba = " ".join(actual + [p])
        if not actual or _m_ancho(draw, prueba, fuente) <= ancho:
            actual.append(p)
        else:
            lineas.append(" ".join(actual))
            actual = [p]
    if actual:
        lineas.append(" ".join(actual))
    return lineas[:max(1, int(max_lineas))]

def _m_glifo(fuente, texto):
    """Ascenso y descenso reales del texto (dibujo de las letras, no de la fuente)."""
    l, t, r, b = fuente.getbbox(texto, anchor="ls")
    return -t, b

def _m_texto(draw, el, texto, path_fonts, ox=0, oy=0):
    if el.get("oculto") or texto is None or str(texto).strip() in ("", "nan", "None"):
        return
    f = _m_fuente(path_fonts, el["fuente"], el["tam"])
    lineas = _m_lineas(draw, texto, f, el["w"], el.get("max_lineas", 1))
    al = el.get("alinear", "izq")
    ax = {"izq": el["x"], "centro": el["x"] + el["w"] / 2, "der": el["x"] + el["w"]}[al]
    anchor = {"izq": "ls", "centro": "ms", "der": "rs"}[al]
    lh = el.get("interlineado", el["tam"] * 1.2)
    for i, ln in enumerate(lineas):
        draw.text((ox + ax, oy + el["y"] + i * lh), ln, font=f, fill=_m_color(el.get("color")), anchor=anchor)

def _m_precio(draw, el, precio_txt, path_fonts, ox=0, oy=0):
    if el.get("oculto"):
        return
    fs = _m_fuente(path_fonts, el.get("fuente_simbolo", el["fuente"]), el["tam_simbolo"])
    fn = _m_fuente(path_fonts, el["fuente"], el["tam_numero"])
    simbolo = el.get("simbolo", "S/")
    tr = el.get("tracking", 0)
    sep = el.get("separacion", 10)
    w_s = _m_ancho(draw, simbolo, fs)
    anchos = [_m_ancho(draw, ch, fn) for ch in precio_txt]
    w_n = sum(anchos) + tr * (len(anchos) - 1)
    total = w_s + sep + w_n
    al = el.get("alinear", "izq")
    izq = {"izq": el["x"], "centro": el["x"] - total / 2, "der": el["x"] - total}[al]
    asc_n, desc_n = _m_glifo(fn, precio_txt)
    asc_s, desc_s = _m_glifo(fs, simbolo)
    if el.get("simbolo_v", "base") == "medio":
        yn = el["y"] + (asc_n - desc_n) / 2
        ys = el["y"] + (asc_s - desc_s) / 2
    else:
        yn = ys = el["y"]
    chapa = el.get("chapa")
    if chapa:
        cy = yn - (asc_n - desc_n) / 2
        h = chapa.get("alto", 100)
        px = chapa.get("pad_x", 20)
        draw.rounded_rectangle([ox + izq - px, oy + cy - h / 2, ox + izq + total + px, oy + cy + h / 2],
                               radius=chapa.get("radio", 15), fill=_m_color(chapa.get("color"), (255, 160, 2)))
    col = _m_color(el.get("color"))
    draw.text((ox + izq, oy + ys), simbolo, font=fs, fill=col, anchor="ls")
    cx = izq + w_s + sep
    for ch, a in zip(precio_txt, anchos):
        draw.text((ox + cx, oy + yn), ch, font=fn, fill=col, anchor="ls")
        cx += a + tr

def _m_legales(draw, el, texto, path_fonts):
    if el.get("oculto"):
        return
    f = _m_fuente(path_fonts, el["fuente"], el["tam"])
    fb = _m_fuente(path_fonts, el.get("fuente_negrita", el["fuente"]), el["tam"])
    cuerpo = str(texto or "").strip()
    if cuerpo.upper().startswith("CONDICIONES GENERALES"):
        cuerpo = cuerpo.split(":", 1)[-1].strip()
    palabras = ["CONDICIONES", "GENERALES:"] + cuerpo.split()
    fuentes = [fb, fb] + [f] * (len(palabras) - 2)
    esp = _m_ancho(draw, " ", f)
    W = el["w"]
    lineas, act, w_act = [], [], 0
    for p, fp in zip(palabras, fuentes):
        wp = _m_ancho(draw, p, fp)
        if act and w_act + esp + wp > W:
            lineas.append(act); act, w_act = [], 0
        w_act = wp if not act else w_act + esp + wp
        act.append((p, fp, wp))
    if act:
        lineas.append(act)
    lh = el.get("interlineado", el["tam"] * 1.3)
    col = _m_color(el.get("color"))
    for i, ln in enumerate(lineas):
        y = el["y"] + i * lh
        ultima = (i == len(lineas) - 1)
        suma = sum(w for _, _, w in ln)
        hueco = esp if (ultima or len(ln) < 2 or not el.get("justificar", True)) else (W - suma) / (len(ln) - 1)
        x = el["x"]
        for p, fp, wp in ln:
            draw.text((x, y), p, font=fp, fill=col, anchor="ls")
            x += wp + hueco

def _m_fecha(draw, el, texto, path_fonts):
    if el.get("oculto") or not str(texto).strip():
        return
    f = _m_fuente(path_fonts, el["fuente"], el["tam"])
    tw = _m_ancho(draw, texto, f)
    w = tw + 2 * el.get("pad_x", 20)
    x0 = el["x"] - w / 2 if el.get("alinear", "centro") == "centro" else el["x"]
    y0, h = el["y"], el.get("h", 44)
    relleno = _m_color(el["relleno"]) if el.get("relleno") else None
    borde = _m_color(el["borde"]) if el.get("borde") else None
    draw.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=el.get("radio", 10), fill=relleno,
                           outline=borde, width=int(el.get("borde_w", 0)) if borde else 0)
    asc, desc = _m_glifo(f, texto)
    draw.text((x0 + w / 2, y0 + h / 2 + (asc - desc) / 2), texto, font=f,
              fill=_m_color(el.get("color")), anchor="ms")

def _m_foto(img, el, url, ox=0, oy=0):
    if el.get("oculto") or not url or str(url).strip() in ("", "nan", "None"):
        return
    try:
        pi = Image.open(BytesIO(requests.get(str(url).strip(), timeout=20).content)).convert("RGBA")
    except Exception as e:
        print(f"⚠️  No se pudo descargar la foto {url}: {e}")
        return
    pi = foto_nitida(pi, (el["w"], el["h"]))
    ah, av = el.get("alinear_h", "centro"), el.get("alinear_v", "medio")
    x = el["x"] + {"izq": 0, "centro": (el["w"] - pi.width) // 2, "der": el["w"] - pi.width}[ah]
    y = el["y"] + {"arriba": 0, "medio": (el["h"] - pi.height) // 2, "abajo": el["h"] - pi.height}[av]
    img.paste(pi, (int(ox + x), int(oy + y)), pi)

def _m_punteada(draw, a, b, color, ancho=2, paso=8):
    (x1, y1), (x2, y2) = a, b
    largo = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    if largo == 0:
        return
    ux, uy = (x2 - x1) / largo, (y2 - y1) / largo
    d = 0
    while d < largo:
        e = min(d + paso, largo)
        draw.line([(x1 + ux * d, y1 + uy * d), (x1 + ux * e, y1 + uy * e)], fill=color, width=ancho)
        d += paso * 2

def _m_precio_txt(valor):
    try:
        return "{:,}".format(int(float(str(valor).replace(",", ""))))
    except Exception:
        return str(valor)

def _m_celdas(grid, n):
    """Posicion (x, y) de cada celda. Con cantidad impar el ultimo va centrado."""
    filas = (n + 1) // 2
    alto_total = filas * grid["celda_h"] + (filas - 1) * grid["gap_y"]
    y0 = grid["y"]
    if grid.get("area_h"):
        y0 += (grid["area_h"] - alto_total) / 2
    pos = []
    for i in range(n):
        col, fila = i % 2, i // 2
        x = grid["x"] + col * (grid["celda_w"] + grid["gap_x"])
        if grid.get("centrar_impar", True) and n % 2 == 1 and i == n - 1 and n > 1:
            x = grid["x"] + (grid["celda_w"] + grid["gap_x"]) / 2
        pos.append((x, y0 + fila * (grid["celda_h"] + grid["gap_y"])))
    return pos

def dibujar_layout(img, draw, lay, data_input, path_fonts):
    """Dibuja una pieza completa a partir de su bloque en LAYOUTS."""
    es_flyer = isinstance(data_input, pd.DataFrame)
    row = data_input.iloc[0] if es_flyer else data_input
    if not es_flyer:
        _m_foto(img, lay.get("foto", {"oculto": True}), row.get('Foto del producto calado'))
        for k, campo in (("marca", "Marca"), ("nombre", "Nombre del producto"), ("sku", "SKU")):
            if k in lay:
                _m_texto(draw, lay[k], row.get(campo), path_fonts)
        if "precio" in lay and tiene_precio(row.get('Precio desc')):
            _m_precio(draw, lay["precio"], _m_precio_txt(row['Precio desc']), path_fonts)
    else:
        if "fecha" in lay:
            _m_fecha(draw, lay["fecha"], str(row.get('Fecha_disponibilidad_flyer', '')).upper(), path_fonts)
        prods = list(data_input.iterrows())[:8]
        n = len(prods)
        grid = lay.get("grid_8") if (n > 6 and lay.get("grid_8")) else lay.get("grid")
        if grid:
            caja_visible = not grid.get("oculto")
            pos = _m_celdas(grid, n)
            est = grid.get("estilo", {})
            for i, ((_, p), (cx, cy)) in enumerate(zip(prods, pos)):
                if caja_visible and (est.get("fondo") or est.get("borde")):
                    draw.rounded_rectangle([cx, cy, cx + grid["celda_w"], cy + grid["celda_h"]],
                                           radius=est.get("radio", 15),
                                           fill=_m_color(est["fondo"]) if est.get("fondo") else None,
                                           outline=_m_color(est["borde"]) if est.get("borde") else None,
                                           width=int(est.get("borde_w", 2)) if est.get("borde") else 0)
            for i, ((_, p), (cx, cy)) in enumerate(zip(prods, pos)):
                el = grid.get("elementos", {})
                _m_foto(img, el.get("foto", {"oculto": True}), p.get('Foto del producto calado') or p.get('Foto'), cx, cy)
                for k, campo in (("marca", "Marca"), ("nombre", "Nombre del producto"), ("sku", "SKU")):
                    if k in el:
                        _m_texto(draw, el[k], p.get(campo), path_fonts, cx, cy)
                if "precio" in el and tiene_precio(p.get('Precio desc')):
                    _m_precio(draw, el["precio"], _m_precio_txt(p['Precio desc']), path_fonts, cx, cy)
            lineas = est.get("lineas")
            if lineas and caja_visible:
                col = _m_color(lineas)
                filas = (n + 1) // 2
                for i, (cx, cy) in enumerate(pos):
                    fila = i // 2
                    if i % 2 == 0 and i + 1 < n and pos[i + 1][1] == cy:
                        xv = cx + grid["celda_w"] + grid["gap_x"] / 2
                        _m_punteada(draw, (xv, cy + 20), (xv, cy + grid["celda_h"] - 20), col)
                    if fila < filas - 1:
                        yh = cy + grid["celda_h"] + grid["gap_y"] / 2
                        _m_punteada(draw, (cx + 20, yh), (cx + grid["celda_w"] - 20, yh), col)
    if "legales" in lay:
        _m_legales(draw, lay["legales"], row.get('Legales'), path_fonts)


def generar_diseno(data_input, color_version="AMARILLO"):
    is_flyer = isinstance(data_input, pd.DataFrame)
    row = data_input.iloc[0] if is_flyer else data_input
    tipo, formato = str(row['Tipo de diseño']).strip(), str(row['Formato']).upper().strip()
    path_fonts, path_fondos = "TIPOGRAFIA/LC", f"FONDOS/LC/{tipo}"

    txt_c = (0,0,0) if color_version == "AMARILLO" else (255,255,255)
    border_c = (254, 215, 0) if color_version == "AMARILLO" else (10, 6, 60)

    # --- AJUSTES POR CAMPAÑA: D("clave") devuelve el desplazamiento, o 0 si no hay ---
    _camp = AJUSTES_CAMPANA.get(tipo.strip().upper(), {})
    def D(clave):
        return _camp.get(formato, {}).get(clave, 0)
    # AJUSTE: 'img_escala' achica o agranda la foto del producto. 1.0 = tamaño original,
    # 0.85 = 15% mas chica. No mueve nada mas; el resto sigue con sus dx/dy.
    _esc = float(_camp.get(formato, {}).get("img_escala", 1.0))
    if _camp.get("texto_color"):
        txt_c = tuple(_camp["texto_color"])

    hay_precio = tiene_precio(row.get('Precio desc'))
    try:
        precio_val = "{:,}".format(int(float(row['Precio desc'])))
    except:
        precio_val = str(row['Precio desc'])

    fname_base = f"LC - {tipo} - {'FLYER' if formato == 'FLYER' else formato}"
    # AJUSTE: se agregan .jpeg/.JPEG. Los flyers estaban exportados en .jpeg y no entraban
    # en la busqueda, asi que generar_diseno devolvia None y el flyer se perdia en silencio.
    EXTENSIONES = [".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"]
    VARIANTES = [f"{fname_base} FONDO {color_version}", f"{fname_base} {color_version}", fname_base]
    full_p = next((os.path.join(path_fondos, f"{v}{e}") for v in VARIANTES for e in EXTENSIONES if os.path.exists(os.path.join(path_fondos, f"{v}{e}"))), None)
    if not full_p:
        # AJUSTE: antes era un return None mudo. Ahora dice exactamente que falta.
        print(f"❌ FONDO NO ENCONTRADO para LC / {tipo} / {formato} / {color_version}. "
              f"Se buscaron estos nombres en '{path_fondos}': "
              f"{[n + e for n in VARIANTES for e in EXTENSIONES]}")
        return None
    img = Image.open(full_p).convert("RGB")
    img = normalizar_lienzo(img, formato, full_p)  # AJUSTE: lienzo a medida oficial antes de pintar
    draw = ImageDraw.Draw(img)

    try:
        f_f = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 24)
        if formato == "STORY":
            f_m = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 53); f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 32); f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 106); f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 42); f_s_ind = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 18); f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 12)
        elif formato == "PPL":
            f_m = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 43); f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 23); f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 85); f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 36); f_s_ind = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 14); f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 11)
        elif formato == "FLYER":
            f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 60); f_s_fly = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 13); f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 16); f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 18); f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 24)
        else:
            f_m = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 34); f_p = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 20); f_pv = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 75); f_ps = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 30); f_s_ind = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 13); f_l = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1.otf", 7)
    except:
        f_m = f_p = f_pv = f_ps = f_s_ind = f_s_fly = f_f = f_l = ImageFont.load_default()

    # LAYOUTS: si esta campaña/formato fue diseñada en el Calibrador, se dibuja con el motor
    _lay = LAYOUTS.get(str(tipo).strip().upper(), {}).get(formato)
    if _lay:
        dibujar_layout(img, draw, _lay, data_input, path_fonts)
    elif formato == "FLYER":
        f_txt = str(row['Fecha_disponibilidad_flyer']).upper()
        wf = draw.textlength(f_txt, font=f_f)
        # AJUSTE: fecha centrada y bajada para que no se solape con el logo de LA CURACAO.
        # La banda amarilla termina en y=308 y los logos bajan hasta y~228, asi que el
        # recuadro (50px de alto) entra justo entre 248 y 298. Antes: pegado a la derecha en 235-285.
        x_fecha = (1080 - (wf + 35)) // 2
        y_fecha_top, y_fecha_bot = 248 + D("fecha_dy"), 298 + D("fecha_dy")
        color_blanco = (255, 255, 255)
        draw.rounded_rectangle([x_fecha, y_fecha_top, x_fecha+wf+35, y_fecha_bot], radius=10, outline=color_blanco, width=3)
        draw.text((x_fecha+(wf+35)//2, (y_fecha_top + y_fecha_bot)//2), f_txt, font=f_f, fill=color_blanco, anchor="mm")

        azul_oscuro = (10, 6, 60)
        num_productos = len(data_input)
        if num_productos <= 6:
            box_w, box_h = 456, 456; img_size = 338; gap_y = 30; y_offset_img = 20
        else:
            box_w, box_h = 456, 375; img_size = 250; gap_y = 15; y_offset_img = 10
        for i, (idx, p) in enumerate(data_input.iterrows()):
            if i >= 8: break
            p_hay_precio = tiene_precio(p.get('Precio desc'))
            try: p_val = "{:,}".format(int(float(p['Precio desc'])))
            except: p_val = str(p['Precio desc'])
            xp = 64 + (i % 2) * (box_w + 40); yp = 340 + D("grid_dy") + (i // 2) * (box_h + gap_y)
            # AJUSTE: con cantidad impar (3, 5, 7) el ultimo producto queda solo en su
            # fila; se centra en vez de quedar pegado a la izquierda.
            if min(num_productos, 8) % 2 == 1 and i == min(num_productos, 8) - 1 and num_productos > 1:
                xp = (1080 - box_w) // 2
            draw.rounded_rectangle([xp, yp, xp+box_w, yp+box_h], radius=15, fill=(255,255,255), outline=border_c, width=2)
            try:
                pi_url = p['Foto del producto calado']; pi = Image.open(BytesIO(requests.get(pi_url).content)).convert("RGBA"); pi = foto_nitida(pi, (img_size, img_size))
                img.paste(pi, (int(xp + (box_w - pi.width) // 2), int(yp + y_offset_img)), pi)
            except: pass

            y_marca_prod = yp + box_h - 86
            f_m_fly = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 20 if len(p['Marca']) < 12 else 16)

            if p_hay_precio:
                # --- Layout original: 2 columnas (marca/nombre | precio/sku) ---
                cl, cr = xp + 114, xp + 342
                draw.text((cl, y_marca_prod), p['Marca'], font=f_m_fly, fill=azul_oscuro, anchor="mm")
                ny = y_marca_prod + 25
                for ln in textwrap.wrap(p['Nombre del producto'], width=18)[:2]:
                    draw.text((cl, ny), ln, font=f_p, fill=azul_oscuro, anchor="mm"); ny += 20
                y_precio = yp + box_h - 57; tw_p = draw.textlength("S/", font=f_ps) + draw.textlength(p_val, font=f_pv) + 8; px_inicio = cr - tw_p // 2
                draw.text((px_inicio, y_precio), "S/", font=f_ps, fill=azul_oscuro, anchor="lm")
                draw.text((px_inicio + draw.textlength("S/", font=f_ps) + 8, y_precio), p_val, font=f_pv, fill=azul_oscuro, anchor="lm")
                draw.text((cr, y_precio + 35), str(p['SKU']), font=f_s_fly, fill=azul_oscuro, anchor="mm")
            else:
                # --- Sin precio: 1 sola columna centrada, SKU debajo del nombre ---
                cc = xp + box_w // 2
                draw.text((cc, y_marca_prod), p['Marca'], font=f_m_fly, fill=azul_oscuro, anchor="mm")
                ny = y_marca_prod + 25
                for ln in textwrap.wrap(p['Nombre del producto'], width=26)[:2]:
                    draw.text((cc, ny), ln, font=f_p, fill=azul_oscuro, anchor="mm"); ny += 20
                draw.text((cc, ny + GAP_SKU_SIN_PRECIO["FLYER"]), str(p['SKU']), font=f_s_fly, fill=azul_oscuro, anchor="mm")

        # AJUSTE: Legales en Blanco para Flyer
        y_legales_fijo = 1815 + D("legales_dy"); f_l_bold = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 16); tit_legal = "CONDICIONES GENERALES: "; cuerpo_legal = str(row['Legales']); ancho_negrita = draw.textlength(tit_legal, font=f_l_bold)
        draw.text((64, y_legales_fijo), tit_legal, font=f_l_bold, fill=color_blanco)
        draw_justified_text(draw, cuerpo_legal, f_l, y_legales_fijo, 64, 1016, color_blanco, line_spacing=2, prefix_width=ancho_negrita)
    else:
        # Otros formatos mantienen txt_c (Amarillo/Blanco según versión)
        pi = Image.open(BytesIO(requests.get(row['Foto del producto calado']).content)).convert("RGBA")
        if formato == "DISPLAY":
            _esc = D("img_escala") or 1.0  # AJUSTE: factor de tamaño de la foto
            pi = foto_nitida(pi, (int(483 * _esc), int(483 * _esc))); img.paste(pi, (423 + D("img_dx"), 25 + D("img_dy")), pi); cx, ny = 255 + D("txt_dx"), 245 + D("txt_dy")
            draw.text((cx, 195 + D("txt_dy")), row['Marca'], font=f_m, fill=txt_c, anchor="mt")
            lineas_nombre = textwrap.wrap(row['Nombre del producto'], width=22)[:2]
            for l in lineas_nombre: draw.text((cx, ny), l, font=f_p, fill=txt_c, anchor="mt"); ny += 27
            if hay_precio:
                # AJUSTE: el precio NO hereda los desplazamientos del texto. Su x y su y se
                # miden desde el layout original, asi que 'precio_dx'/'precio_dy' son
                # absolutos y no se suman a 'txt_dx'/'txt_dy' (antes se duplicaban y el
                # bloque se salia del lienzo por la izquierda).
                cx_precio = 255 + D("precio_dx")
                _ny_base = ny - D("txt_dy")
                tw = draw.textlength("S/", font=f_ps) + draw.textlength(precio_val, font=f_pv) + 15
                px = cx_precio - tw//2
                if px < 20:
                    print(f"⚠️  PRECIO FUERA DEL LIENZO en DISPLAY / {tipo}: empezaria en x={int(px)}. "
                          f"Se recorta a x=20; baja el valor absoluto de 'precio_dx'.")
                    px = 20
                _y_prec = _ny_base + 55 + D("precio_dy")
                draw.text((px, _y_prec), "S/ ", font=f_ps, fill=txt_c, anchor="lm"); draw.text((px + draw.textlength("S/ ", font=f_ps) + 15, _y_prec), precio_val, font=f_pv, fill=txt_c, anchor="lm")
                draw.text((cx_precio, _ny_base + 100 + D("precio_dy")), str(row['SKU']), font=f_s_ind, fill=txt_c, anchor="mt")
            else:
                # Sin precio: el SKU sube y queda pegado al nombre
                draw.text((cx, ny + GAP_SKU_SIN_PRECIO["DISPLAY"]), str(row['SKU']), font=f_s_ind, fill=txt_c, anchor="mt")
            f_l_bold = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 7); tit_legal = "CONDICIONES GENERALES: "; cuerpo_legal = str(row['Legales']); ancho_negrita = draw.textlength(tit_legal, font=f_l_bold)
            draw.text((40, 480 + D("legales_dy")), tit_legal, font=f_l_bold, fill=txt_c)
            draw_justified_text(draw, cuerpo_legal, f_l, y_start=480 + D("legales_dy"), x_start=40, x_end=960, fill=txt_c, line_spacing=2, prefix_width=ancho_negrita)
        elif formato == "STORY":
            # AJUSTE: foto centrada en el lienzo real y subida 50px para despegarla del texto
            _esc = D("img_escala") or 1.0  # AJUSTE: factor de tamaño de la foto
            pi = afilar(pi.resize((int(845 * _esc), int(845 * _esc)), Image.Resampling.LANCZOS, reducing_gap=None))
            img.paste(pi, ((1080 - pi.width) // 2 + D("img_dx"), 640 + D("img_dy")), pi)   # antes (140, 690) -> centro caía en x=562
            cx_textos, anchor_y_textos = STORY_MARGEN + D("txt_dx"), 1542 + D("txt_dy")
            draw.text((cx_textos, anchor_y_textos), row['Marca'], font=f_m, fill=txt_c, anchor="lt"); ny = anchor_y_textos + 65
            lineas_nombre = textwrap.wrap(row['Nombre del producto'], width=22 if hay_precio else 34)[:2]
            for l in lineas_nombre: draw.text((cx_textos, ny), l, font=f_p, fill=txt_c, anchor="lt"); ny += 40
            if hay_precio:
                anchor_y_precio, p_v, espacio_entre_simbolo = 1600 + D("precio_dy"), precio_val, 20
                tw = draw.textlength("S/", font=f_ps) + draw.textlength(p_v, font=f_pv) + espacio_entre_simbolo
                # AJUSTE: el bloque de precio cierra en el margen derecho, espejo del texto de la izquierda
                px_bloque_completo = (1080 - STORY_MARGEN) - tw + D("precio_dx")   # antes: 810 - tw//2
                cx_precio = px_bloque_completo + tw // 2
                draw.text((px_bloque_completo, anchor_y_precio), "S/", font=f_ps, fill=txt_c, anchor="ls"); px_numero = px_bloque_completo + draw.textlength("S/", font=f_ps) + espacio_entre_simbolo; draw.text((px_numero, anchor_y_precio), p_v, font=f_pv, fill=txt_c, anchor="ls")
                draw.text((cx_precio, anchor_y_precio + 40), str(row['SKU']), font=f_s_ind, fill=txt_c, anchor="mt")  # AJUSTE: sigue al bloque, antes fijo en 810
            else:
                # Sin precio: 1 sola columna, SKU debajo del nombre
                draw.text((cx_textos, ny + GAP_SKU_SIN_PRECIO["STORY"]), str(row['SKU']), font=f_s_ind, fill=txt_c, anchor="lt")
            f_l_bold = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 12); tit_legal = "CONDICIONES GENERALES: "; cuerpo_legal = str(row['Legales']); ancho_negrita = draw.textlength(tit_legal, font=f_l_bold); draw.text((65, 1797 + D("legales_dy")), tit_legal, font=f_l_bold, fill=txt_c)
            draw_justified_text(draw, cuerpo_legal, f_l, y_start=1797 + D("legales_dy"), x_start=65, x_end=1015, fill=txt_c, line_spacing=2, prefix_width=ancho_negrita)
        elif formato == "PPL":
            _esc = D("img_escala") or 1.0  # AJUSTE: factor de tamaño de la foto
            pi = foto_nitida(pi, (int(779 * _esc), int(598 * _esc))); canvas_width = 1080; px_centrado = (canvas_width - pi.width) // 2
            py_posicion = 210 + D("img_dy")  # AJUSTE: sube la foto del producto (antes 240)
            img.paste(pi, (px_centrado + D("img_dx"), py_posicion), pi); y_base_alineacion, y_precio = 850 + D("txt_dy"), 865 + D("precio_dy")
            if hay_precio:
                p_v, w_simbolo, w_monto, espacio_interno = precio_val, draw.textlength("S/", font=f_ps), draw.textlength(precio_val, font=f_pv), 15
                tw_precio = w_simbolo + w_monto + espacio_interno; eje_x_derecha = 820 + D("precio_dx"); px_inicio_bloque = eje_x_derecha - tw_precio // 2
                draw.text((px_inicio_bloque, y_precio), "S/", font=f_ps, fill=txt_c, anchor="ls"); px_numero = px_inicio_bloque + w_simbolo + espacio_interno; draw.text((px_numero, y_precio), p_v, font=f_pv, fill=txt_c, anchor="ls"); draw.text((eje_x_derecha, y_precio + 30), str(row['SKU']), font=f_s_ind, fill=txt_c, anchor="mt")
            cx = 200 + D("txt_dx"); draw.text((cx, y_base_alineacion), row['Marca'], font=f_m, fill=txt_c, anchor="ls"); ny = y_base_alineacion + 10
            lineas_nombre = textwrap.wrap(row['Nombre del producto'], width=25 if hay_precio else 40)[:2]
            for l in lineas_nombre: draw.text((cx, ny), l, font=f_p, fill=txt_c, anchor="lt"); ny += 30
            if not hay_precio:
                # Sin precio: 1 sola columna, SKU debajo del nombre
                draw.text((cx, ny + GAP_SKU_SIN_PRECIO["PPL"]), str(row['SKU']), font=f_s_ind, fill=txt_c, anchor="lt")
            f_l_bold = ImageFont.truetype(f"{path_fonts}/HurmeGeometricSans1 Bold.otf", 11); tit_legal = "CONDICIONES GENERALES: "; cuerpo_legal = str(row['Legales']); ancho_negrita = draw.textlength(tit_legal, font=f_l_bold); draw.text((50, 985 + D("legales_dy")), tit_legal, font=f_l_bold, fill=txt_c)
            draw_justified_text(draw, cuerpo_legal, f_l, y_start=985 + D("legales_dy"), x_start=50, x_end=1030, fill=txt_c, line_spacing=2, prefix_width=ancho_negrita)

    sku_limpio = str(row['SKU'] or row['ID_Flyer']).replace("/", "-").replace("\\", "-")
    fname = f"{sku_limpio}_{formato}_{color_version}.jpg"
    img.save(f"output/{fname}", quality=100, subsampling=0); return f"{RAW_URL}{fname}"

def resolver_columna(df, nombre_buscado):
    """Devuelve el nombre REAL de la columna en df que coincide con nombre_buscado
    ignorando mayúsculas/minúsculas y espacios extra. None si no existe ninguna."""
    objetivo = nombre_buscado.strip().lower()
    for c in df.columns:
        if c.strip().lower() == objetivo:
            return c
    return None

# --- BUCLE DE EJECUCIÓN PRINCIPAL ---
data, res_sheet, viejos = get_sheets_data()

# FIX: cada script solo debe procesar sus propias filas, nunca las de la otra marca
col_tienda = resolver_columna(data, 'Tienda')
if col_tienda is None:
    print(f"❌ No se encontró una columna 'Tienda' en Hoja 1. Columnas disponibles: {list(data.columns)}")
    raise SystemExit(1)
data = data[data[col_tienda].astype(str).str.strip().str.upper() == 'LC'].reset_index(drop=True)

os.makedirs('output', exist_ok=True)
h_lima = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")
archivos_generados = 0
filas_para_google = []

print(f"DEBUG: Filas LC detectadas (columna real: '{col_tienda}'): {len(data)}")

def hay_que_generar(llave, nombre_archivo, tipo_camp=""):
    """True si la pieza falta: o no esta registrada en 'Resultados', o su archivo
    ya no existe en output/ (p.ej. despues de una limpieza del repo), o su campaña
    esta en FORZAR_REGENERAR.
    AJUSTE: antes solo miraba el Sheet, asi que si se borraban las imagenes el
    script las saltaba igual y todos los links quedaban en 404."""
    if str(tipo_camp).strip().upper() in FORZAR_REGENERAR:
        print(f"🔁 {llave}: campaña en FORZAR_REGENERAR, se vuelve a dibujar.")
        return True
    if llave not in viejos:
        return True
    if not os.path.exists(os.path.join("output", nombre_archivo)):
        print(f"♻️  {llave} esta en Resultados pero falta output/{nombre_archivo}. Se regenera.")
        return True
    return False

for idx, row in data.iterrows():
    f_v = str(row['Formato']).upper().strip()
    if f_v in ["FLYER", "", "0"]: continue

    tipo_camp = str(row['Tipo de diseño']).strip().upper()
    # AJUSTE: el fondo AZUL se retira. Todas las piezas salen solo en AMARILLO.
    versiones = ["AMARILLO"]
    for c in versiones:
        sku_val = str(row['SKU']).replace("/", "-").replace("\\", "-")
        llave = f"{sku_val}_{f_v}_{c}".upper()
        archivo = f"{sku_val}_{f_v}_{c}.jpg"
        _era_nueva = llave not in viejos
        if hay_que_generar(llave, archivo, row['Tipo de diseño']):
            print(f"🎨 Generando pieza: {llave}")
            url = generar_diseno(row, c)
            # Si la llave ya existia, solo se repone el archivo: la fila del Sheet
            # ya apunta a esa URL, asi que no se duplica el registro.
            if url and _era_nueva:
                # AJUSTE: se agrega TIENDA_SCRIPT en la posicion 3 (columna C).
                # Antes se mandaban 6 valores y todo quedaba corrido una columna a la
                # izquierda, por eso habia que escribir "LC" a mano en el Sheet.
                # AJUSTE: columna H 'Link web' con el link del feed segun el SKU.
                # Orden: Fecha | ID | Tienda | Diseño | Formato | Color | Link Imagen | Link web
                lw = link_web(TIENDA_SCRIPT, row['SKU'])
                filas_para_google.append([h_lima, llave, TIENDA_SCRIPT, row['Tipo de diseño'], f_v, c, url, lw])
                archivos_generados += 1

fly_g = data[data['Formato'].astype(str).str.upper().str.strip() == "FLYER"]
for id_f, group in fly_g.groupby('ID_Flyer'):
    if str(id_f) in ["0", "0.0", ""]: continue
    tipo_camp = str(group.iloc[0]['Tipo de diseño']).strip().upper()
    # AJUSTE: el fondo AZUL se retira. Todos los flyers salen solo en AMARILLO.
    versiones = ["AMARILLO"]
    for c in versiones:
        llave = f"{id_f}_FLYER_{c}".upper()
        # El archivo del flyer se nombra con el SKU del PRIMER producto del grupo
        # (asi lo guarda generar_diseno), no con el ID_Flyer.
        _sku_fly = str(group.iloc[0]['SKU'] or id_f).replace("/", "-").replace("\\", "-")
        archivo = f"{_sku_fly}_FLYER_{c}.jpg"
        _era_nueva = llave not in viejos
        if hay_que_generar(llave, archivo, group.iloc[0]['Tipo de diseño']):
            print(f"🎨 Generando Flyer: {llave}")
            url = generar_diseno(group, c)
            if url and _era_nueva:
                # AJUSTE: mismo fix de columna Tienda que en el ciclo de piezas individuales
                # AJUSTE: link web del flyer = link del primer SKU del grupo (ver FLYER_USA_PRIMER_SKU)
                lw = link_web(TIENDA_SCRIPT, group.iloc[0]['SKU']) if FLYER_USA_PRIMER_SKU else TEXTO_SIN_FEED
                filas_para_google.append([h_lima, llave, TIENDA_SCRIPT, group.iloc[0]['Tipo de diseño'], "FLYER", c, url, lw])
                archivos_generados += 1

if filas_para_google:
    res_sheet.append_rows(filas_para_google)
    print(f"✅ Éxito: Se registraron {len(filas_para_google)} piezas nuevas.")

if archivos_generados == 0:
    print("⚠️ No se generaron archivos nuevos.")
    with open("last_run.txt", "w") as f:
        f.write(f"Sin cambios: {h_lima}")
