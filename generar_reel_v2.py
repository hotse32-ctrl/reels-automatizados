import os
import re
import sys
import json
import unicodedata
import argparse

import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Compatibilidad: Pillow >= 10 eliminó Image.ANTIALIAS, pero moviepy 1.0.3
# todavía lo usa internamente al hacer resize() de video. Este shim lo repara.
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

from moviepy.editor import (
    VideoFileClip, ImageClip, CompositeVideoClip, CompositeAudioClip,
    AudioFileClip, concatenate_videoclips, concatenate_audioclips
)
from moviepy.audio.fx.all import audio_loop, volumex
from moviepy.audio.AudioClip import AudioClip

from gtts import gTTS
import google.generativeai as genai

# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FB_ACCESS_TOKEN = os.environ.get("FACEBOOK_ACCESS_TOKEN")
PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID")
YOUTUBE_TOKEN_JSON = os.environ.get("YOUTUBE_TOKEN_JSON")

W, H = 720, 1280
FPS = 24
VIDEO_BASE_PATH = "assets/video_base.mp4"

WPM = 150.0
SEG_POR_PALABRA = 60.0 / WPM        # 0.4s por palabra
PAUSA_FRASE = 1.5                    # segundos de texto fijo tras revelar la frase
FADE_OUT = 0.3
BLANCO_TRANSICION = 0.2
FADE_IN = 0.3

FONT_SIZE = 60
MAX_ANCHO_TEXTO = int(W * 0.7)  # 70% del ancho, según especificación

COLOR_BLANCO = (255, 255, 255, 255)
COLOR_ROJO = (220, 0, 0, 255)
COLOR_SOMBRA = (0, 0, 0, 160)

os.makedirs("output", exist_ok=True)

# ============================================================
# LOS 10 TEMAS FIJOS (rotan todos los días)
# ============================================================
TEMAS = [
    {
        "id": 1,
        "nombre": "El poder del silencio",
        "sonido_url": "https://cdn.pixabay.com/download/audio/2025/05/31/audio_8541960f00.mp3?filename=universfield-old-clock-ticking-352288.mp3",
        "ejemplo_guion": "El silencio no es vacio. Es un arma. Quien lo usa, controla. Te hace dudar de ti mismo. Buscas aprobacion. Y el no te la da. Eso es poder. El silencio te desarma. Y tu, sin saberlo, ya perdiste.",
        "ejemplo_keywords": ["arma", "controla", "dudar", "poder", "desarma", "perdiste"],
    },
    {
        "id": 2,
        "nombre": "Ghosting: el abandono",
        "sonido_url": "https://cdn.pixabay.com/download/audio/2025/06/23/audio_8db020ee6c.mp3?filename=dragon-studio-water-dripping-364450.mp3",
        "ejemplo_guion": "Desaparecio sin aviso. No hubo adios. Solo vacio. Te dejo con preguntas. ¿Que hiciste mal? Nada. El problema no eras tu. Era su cobardia. No vuelvas a buscar quien no te busco.",
        "ejemplo_keywords": ["desaparecio", "vacio", "preguntas", "nada", "cobardia", "no vuelvas"],
    },
    {
        "id": 3,
        "nombre": "Rompe la jaula mental",
        "sonido_url": "https://cdn.pixabay.com/download/audio/2025/10/28/audio_a61f2bf9d0.mp3?filename=dragon-studio-fire-crackling-sounds-427410.mp3",
        "ejemplo_guion": "Tu mente es una jaula. Tu mismo la construiste. Con miedos. Con excusas. Pero la llave esta en tu mano. Rompe los barrotes. Duele al salir. Pero fuera hay aire. Y tu mereces respirar.",
        "ejemplo_keywords": ["jaula", "construiste", "miedos", "llave", "rompe", "duele", "respirar"],
    },
    {
        "id": 4,
        "nombre": "El narcisista y tu reflejo",
        "sonido_url": "https://cdn.pixabay.com/download/audio/2026/02/02/audio_6f85ca26ca.mp3?filename=dragon-studio-eerie-wind-478386.mp3",
        "ejemplo_guion": "Te miro y te cambio. Poco a poco. Sin que lo notes. Tu reflejo ya no es tuyo. Es lo que el queria ver. Te vacio de ti mismo. Y lleno el hueco con dudas. Despierta. Recupera tu rostro.",
        "ejemplo_keywords": ["cambio", "reflejo", "vacio", "dudas", "despierta", "recupera"],
    },
    {
        "id": 5,
        "nombre": "Mereces mas que migajas",
        "sonido_url": "https://cdn.pixabay.com/download/audio/2022/01/18/audio_3fbeac9dbc.mp3?filename=freesound_community-soft-rain-on-a-tile-roof-14515.mp3",
        "ejemplo_guion": "No vivas de migajas. Tu no sobras. Mereces un plato lleno. Alguien que se quede. No que aparezca cuando le conviene. El amor no mendiga. Se elige. Y tu, desde hoy, te eliges a ti.",
        "ejemplo_keywords": ["migajas", "sobras", "mereces", "quede", "eliges"],
    },
    {
        "id": 6,
        "nombre": "La manipulacion que no ves",
        "sonido_url": "https://cdn.pixabay.com/download/audio/2022/03/14/audio_c320063f20.mp3?filename=freesound_community-1-wood-staircase-old-creaking-footsteps-62079.mp3",
        "ejemplo_guion": "No te gritan. Te susurran dudas. Hacen que creas que es tu culpa. Que estas loco. Que exageras. Asi te doman. Sin que levantes la voz. La manipulacion no se ve. Se siente. Y tu lo sientes.",
        "ejemplo_keywords": ["susurran", "culpa", "loco", "doman", "manipulacion", "sientes"],
    },
    {
        "id": 7,
        "nombre": "Renacer despues de caer",
        "sonido_url": "https://cdn.pixabay.com/download/audio/2022/08/09/audio_440031caee.mp3?filename=gregorquendel-designed-fire-winds-swoosh-04-116788.mp3",
        "ejemplo_guion": "Caiste. Dolio. Te quedaste en el suelo. Pero el suelo no es tu lugar. Nadie va a levantarte. Solo tu. Y duele. Pero el dolor es temporal. Tu grandeza, eterna. Levantate.",
        "ejemplo_keywords": ["caiste", "dolio", "suelo", "levantarte", "duele", "grandeza", "levantate"],
    },
    {
        "id": 8,
        "nombre": "Dependencia emocional",
        "sonido_url": "https://cdn.pixabay.com/download/audio/2022/03/24/audio_fd3a6df648.mp3?filename=freesound_community-pouring-glass-of-water-104819.mp3",
        "ejemplo_guion": "Sin el no eres nada. Eso te hizo creer. Pero es mentira. Tu existias antes. Existiras despues. Corta el cordon. Aunque duela. Aunque llores. Al otro lado, hay paz. Y te espera.",
        "ejemplo_keywords": ["nada", "mentira", "existias", "cordon", "duela", "paz"],
    },
    {
        "id": 9,
        "nombre": "La verdad que duele",
        "sonido_url": "https://cdn.pixabay.com/download/audio/2026/02/10/audio_a52e03582a.mp3?filename=dragon-studio-dry-leaves-rustling-482874.mp3",
        "ejemplo_guion": "Prefieres la mentira. Es mas comoda. Pero la mentira te ata. La verdad duele. Pero te suelta. El miedo a ver, es peor que ver. Abre los ojos. Aunque duela. Del otro lado, eres libre.",
        "ejemplo_keywords": ["mentira", "ata", "verdad", "suelta", "miedo", "libre"],
    },
    {
        "id": 10,
        "nombre": "Tu eres tu propia salvacion",
        "sonido_url": "https://cdn.pixabay.com/download/audio/2025/10/18/audio_7925a4c8d7.mp3?filename=eryliaa-soft-rain-on-window-glass-422406.mp3",
        "ejemplo_guion": "Esperaste a alguien. Que te rescatara. Pero nunca llego. Porque no tenia que hacerlo. Tu siempre tuviste el poder. Estaba en ti. Solo no lo veias. Ahora si. Salvate tu mismo. Hoy.",
        "ejemplo_keywords": ["rescatara", "poder", "ti", "veias", "salvate", "hoy"],
    },
]


# ============================================================
# UTILIDADES DE TEXTO
# ============================================================
def quitar_ene(texto):
    """Devuelve True si el texto NO contiene ninguna Ñ/ñ (válido)."""
    return "ñ" not in texto.lower()


def normalizar_palabra(p):
    """Quita puntuación y tildes para comparar contra la lista de palabras clave."""
    p = p.strip(".,;:!?¿¡\"'()")
    p = unicodedata.normalize("NFKD", p).encode("ascii", "ignore").decode("ascii")
    return p.lower()


def dividir_en_frases(guion):
    """Divide el guion en frases cortas usando el punto como separador."""
    partes = [p.strip() for p in guion.split(".") if p.strip()]
    return [p + "." for p in partes]


# ============================================================
# 1. GENERAR GUION CON GEMINI (por tema, con reglas estrictas)
# ============================================================
def generar_guion(tema, model):
    prompt = f"""Eres un guionista experto en contenido motivacional y de psicologia emocional para Reels/Shorts en español.

Tema del día: "{tema['nombre']}"

Escribe un guion de voz en off de 65 a 70 palabras, en segundo persona ("tu"), tono dramático y reflexivo,
con frases cortas separadas por puntos (como golpes de efecto), igual al estilo de este ejemplo (NO lo copies, solo imita el estilo y el largo):

"{tema['ejemplo_guion']}"

REGLAS OBLIGATORIAS:
1. Entre 65 y 70 palabras en total.
2. PROHIBIDO usar la letra "Ñ" o "ñ" en cualquier palabra (ninguna excepción, ni siquiera en "año", "pequeño", "señal", etc. — evita esas palabras por completo, usa sinónimos).
3. Frases cortas, separadas por puntos.
4. Español neutro, tono dramático/reflexivo, segunda persona.
5. Marca entre 5 y 7 "palabras clave" del guion (las palabras más impactantes, tal como estén escritas en el guion, sin puntuación).

Responde ÚNICAMENTE con un JSON válido, sin texto adicional, con este formato exacto:
{{"guion": "texto del guion aqui", "palabras_clave": ["palabra1", "palabra2", "palabra3"]}}
"""

    ultimo_error = None
    for intento in range(3):
        try:
            respuesta = model.generate_content(prompt)
            texto = respuesta.text.strip()
            texto = re.sub(r"^```json\s*|\s*```$", "", texto.strip(), flags=re.MULTILINE).strip()
            data = json.loads(texto)
            guion = data["guion"].strip()
            palabras_clave = [normalizar_palabra(p) for p in data.get("palabras_clave", [])]

            if not quitar_ene(guion):
                ultimo_error = "El guion generado contiene la letra Ñ"
                print(f"⚠️ Intento {intento+1}: {ultimo_error}, reintentando...")
                continue

            num_palabras = len(guion.split())
            if num_palabras < 50 or num_palabras > 90:
                ultimo_error = f"Largo fuera de rango ({num_palabras} palabras)"
                print(f"⚠️ Intento {intento+1}: {ultimo_error}, reintentando...")
                continue

            print(f"✅ Guion generado para tema '{tema['nombre']}' ({num_palabras} palabras)")
            return guion, palabras_clave

        except Exception as e:
            ultimo_error = str(e)
            print(f"⚠️ Intento {intento+1} falló al generar guion: {e}")

    print(f"❌ No se pudo generar guion válido tras 3 intentos ({ultimo_error}). Usando guion de ejemplo de respaldo.")
    return tema["ejemplo_guion"], tema["ejemplo_keywords"]


# ============================================================
# 2. AUDIO DE NARRACIÓN (gTTS)
# ============================================================
def generar_audio_narracion(texto, ruta_salida):
    try:
        tts = gTTS(text=texto, lang="es", slow=False)
        tts.save(ruta_salida)
        print("✅ Audio de narración generado")
        return True
    except Exception as e:
        print(f"❌ Error al generar audio de narración: {e}")
        return False


# ============================================================
# 3. DESCARGAR SONIDO AMBIENTAL
# ============================================================
def descargar_sonido_ambiental(url, ruta_salida):
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        with open(ruta_salida, "wb") as f:
            f.write(r.content)
        print("✅ Sonido ambiental descargado")
        return True
    except Exception as e:
        print(f"❌ Error al descargar sonido ambiental: {e}")
        return False


# ============================================================
# 4. FUENTE (Montserrat Bold, descargada en tiempo de ejecución)
# ============================================================
def obtener_fuente(tamano):
    """Descarga Montserrat (fuente variable) y la fija en peso Bold (700).
    Google Fonts migró Montserrat a un único archivo de fuente variable
    (ya no existe un .ttf 'Bold' estático separado), así que se descarga
    Montserrat[wght].ttf y se selecciona el peso 700 vía set_variation_by_axes."""
    ruta_local = os.environ.get("FONT_PATH")
    if ruta_local and os.path.exists(ruta_local):
        return ImageFont.truetype(ruta_local, tamano)

    ruta_descarga = "output/Montserrat-Variable.ttf"
    if not os.path.exists(ruta_descarga):
        try:
            url = "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf"
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            with open(ruta_descarga, "wb") as f:
                f.write(r.content)
            print("✅ Fuente Montserrat (variable) descargada")
        except Exception as e:
            print(f"⚠️ No se pudo descargar Montserrat: {e}")

    if os.path.exists(ruta_descarga):
        font = ImageFont.truetype(ruta_descarga, tamano)
        try:
            font.set_variation_by_axes([700])  # 700 = Bold
            print("✅ Peso Bold (700) aplicado a Montserrat")
        except Exception as e:
            print(f"⚠️ No se pudo fijar el peso Bold de la fuente variable: {e}")
        return font

    for c in [
        "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]:
        if os.path.exists(c):
            print(f"⚠️ Usando fuente de respaldo: {c}")
            return ImageFont.truetype(c, tamano)

    return ImageFont.load_default()


# ============================================================
# 5. CONSTRUCCIÓN DE SUBTÍTULOS ANIMADOS (palabra por palabra)
# ============================================================
def envolver_en_lineas(palabras, font, draw, max_ancho, max_lineas=2):
    """Distribuye la lista completa de palabras en hasta `max_lineas` líneas,
    respetando el ancho máximo. Devuelve una lista de listas de palabras (una por línea)."""
    lineas = []
    linea_actual = []
    for palabra in palabras:
        prueba = linea_actual + [palabra]
        ancho = draw.textlength(" ".join(prueba), font=font)
        if ancho <= max_ancho or not linea_actual:
            linea_actual = prueba
        else:
            lineas.append(linea_actual)
            linea_actual = [palabra]
        if len(lineas) >= max_lineas:
            break
    if linea_actual and len(lineas) < max_lineas:
        lineas.append(linea_actual)
    return lineas


def renderizar_estado(lineas_completas, num_palabras_visibles, palabras_clave, font):
    """Dibuja el estado actual del subtítulo (con `num_palabras_visibles` palabras reveladas)
    y devuelve una imagen RGBA de tamaño WxH."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    todas_palabras = [p for linea in lineas_completas for p in linea]
    visibles = todas_palabras[:num_palabras_visibles]

    # Reconstruir qué palabras visibles caen en cada línea
    idx = 0
    lineas_render = []
    for linea in lineas_completas:
        n = len(linea)
        vis_en_linea = visibles[idx:idx + n]
        lineas_render.append(vis_en_linea)
        idx += n

    alto_linea = int(FONT_SIZE * 13 / 100 * 100 / 100) or FONT_SIZE + 20
    alto_linea = FONT_SIZE + 22
    lineas_no_vacias = [l for l in lineas_render if l]
    alto_total = alto_linea * max(len(lineas_no_vacias), 1)
    y = (H - alto_total) // 2

    for linea in lineas_render:
        if not linea:
            continue
        texto_linea = " ".join(linea)
        ancho_total = draw.textlength(texto_linea, font=font)
        x = (W - ancho_total) / 2

        for palabra in linea:
            clave = normalizar_palabra(palabra) in palabras_clave
            color = COLOR_ROJO if clave else COLOR_BLANCO
            # sombra
            draw.text((x + 3, y + 3), palabra, font=font, fill=COLOR_SOMBRA)
            draw.text((x, y), palabra, font=font, fill=color)
            x += draw.textlength(palabra + " ", font=font)
        y += alto_linea

    return img


def construir_clip_subtitulos(guion, palabras_clave, font):
    """Construye el CompositeVideoClip de subtítulos animados para todo el guion
    y devuelve (clip_subtitulos, duracion_total_segundos)."""
    frases = dividir_en_frases(guion)
    img_dummy = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_dummy = ImageDraw.Draw(img_dummy)

    clips = []
    tiempo_actual = 0.0

    for i, frase in enumerate(frases):
        palabras = frase.split()
        lineas = envolver_en_lineas(palabras, font, draw_dummy, MAX_ANCHO_TEXTO, max_lineas=2)
        total_palabras = sum(len(l) for l in lineas)

        # Estados: revelar palabra por palabra
        for n in range(1, total_palabras + 1):
            img = renderizar_estado(lineas, n, palabras_clave, font)
            duracion = SEG_POR_PALABRA
            if n == total_palabras:
                duracion += PAUSA_FRASE  # última palabra se queda fija 1.5s extra
            clip = ImageClip(np.array(img)).set_duration(duracion)
            clips.append(clip)

        # Transición entre frases (no aplica después de la última)
        if i < len(frases) - 1:
            # fade out de la última imagen de esta frase
            clips[-1] = clips[-1].crossfadeout(FADE_OUT)
            blanco = ImageClip(np.array(img_dummy)).set_duration(BLANCO_TRANSICION)
            clips.append(blanco)

    secuencia = concatenate_videoclips(clips, method="compose")

    # fade-in de la primera palabra de cada frase (excepto la primera del video)
    return secuencia, secuencia.duration


# ============================================================
# 6. CONSTRUIR VIDEO FINAL DE UN TEMA
# ============================================================
def construir_video_tema(tema, guion, palabras_clave, ruta_salida):
    font = obtener_fuente(FONT_SIZE)

    print("🎬 Construyendo subtítulos animados...")
    clip_subtitulos, duracion_total = construir_clip_subtitulos(guion, palabras_clave, font)
    print(f"   Duración calculada por subtítulos: {duracion_total:.1f}s")

    # --- Video base loopeado hasta cubrir la duración total ---
    print("🎥 Preparando video base...")
    video_original = VideoFileClip(VIDEO_BASE_PATH).resize((W, H))
    n_loops = int(duracion_total // video_original.duration) + 1
    video_loop = concatenate_videoclips([video_original] * n_loops).subclip(0, duracion_total)

    # --- Audio de narración ---
    ruta_audio_narracion = "output/narracion.mp3"
    ok_audio = generar_audio_narracion(guion, ruta_audio_narracion)
    if ok_audio and os.path.exists(ruta_audio_narracion):
        audio_narracion = AudioFileClip(ruta_audio_narracion)
        if audio_narracion.duration < duracion_total:
            silencio = AudioClip(lambda t: [0, 0], duration=duracion_total - audio_narracion.duration)
            audio_narracion = concatenate_audioclips([audio_narracion, silencio])
        else:
            audio_narracion = audio_narracion.subclip(0, duracion_total)
    else:
        audio_narracion = AudioClip(lambda t: [0, 0], duration=duracion_total)

    # --- Sonido ambiental de fondo ---
    ruta_sonido = "output/ambiente.mp3"
    audio_ambiente = None
    if descargar_sonido_ambiental(tema["sonido_url"], ruta_sonido):
        try:
            amb = AudioFileClip(ruta_sonido)
            amb = audio_loop(amb, duration=duracion_total)
            audio_ambiente = volumex(amb, 0.25)
        except Exception as e:
            print(f"⚠️ No se pudo procesar el sonido ambiental: {e}")

    if audio_ambiente is not None:
        audio_final = CompositeAudioClip([audio_ambiente, volumex(audio_narracion, 1.0)])
    else:
        audio_final = audio_narracion

    audio_final = audio_final.set_duration(duracion_total)

    # --- Composición final ---
    video_final = CompositeVideoClip([video_loop, clip_subtitulos.set_position(("center", "center"))])
    video_final = video_final.set_audio(audio_final).set_duration(duracion_total)

    video_final.write_videofile(
        ruta_salida, fps=FPS, codec="libx264", audio_codec="aac",
        threads=4, verbose=False, logger=None
    )
    print(f"✅ Video final generado: {ruta_salida}")
    return duracion_total


# ============================================================
# 7. PUBLICACIÓN
# ============================================================
def publicar_facebook(ruta_video, titulo, descripcion):
    try:
        url_fb = f"https://graph.facebook.com/v19.0/{PAGE_ID}/videos"
        files = {"source": open(ruta_video, "rb")}
        data = {
            "access_token": FB_ACCESS_TOKEN,
            "title": titulo,
            "description": descripcion,
            "published": "true",
        }
        resp = requests.post(url_fb, files=files, data=data, timeout=180)
        if resp.status_code == 200:
            print("✅ Publicado en Facebook:", resp.json())
        else:
            print(f"❌ Error en Facebook: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"❌ Excepción al publicar en Facebook: {e}")


def publicar_youtube(ruta_video, titulo, descripcion):
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        with open("youtube_token.json", "w") as f:
            f.write(YOUTUBE_TOKEN_JSON)
        creds = Credentials.from_authorized_user_file("youtube_token.json")
        youtube = build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {
                "title": titulo,
                "description": descripcion,
                "tags": ["motivacion", "superacion", "psicologia", "shorts", "reflexion"],
                "categoryId": "22",
            },
            "status": {"privacyStatus": "unlisted", "selfDeclaredMadeForKids": False},
        }
        media = MediaFileUpload(ruta_video, chunksize=-1, resumable=True)
        req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        resp = req.execute()
        print("✅ Publicado en YouTube:", resp["id"], f"https://youtu.be/{resp['id']}")
    except Exception as e:
        print(f"❌ Error al publicar en YouTube: {e}")


# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tema", type=int, default=None, help="ID de un solo tema a procesar (1-10). Si se omite, procesa los 10.")
    parser.add_argument("--no-publicar", action="store_true", help="Genera el video pero no publica (para pruebas).")
    args = parser.parse_args()

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-flash-latest")

    temas_a_procesar = [t for t in TEMAS if t["id"] == args.tema] if args.tema else TEMAS

    for tema in temas_a_procesar:
        print(f"\n========== TEMA {tema['id']}: {tema['nombre']} ==========")
        try:
            guion, palabras_clave = generar_guion(tema, model)
            ruta_salida = f"output/reel_tema{tema['id']}.mp4"
            construir_video_tema(tema, guion, palabras_clave, ruta_salida)

            if not args.no_publicar:
                titulo = tema["nombre"]
                descripcion = guion
                publicar_facebook(ruta_salida, titulo, descripcion)
                publicar_youtube(ruta_salida, titulo, descripcion)
            else:
                print("⏭️ --no-publicar activado, video generado pero no publicado.")

        except Exception as e:
            print(f"❌ Error procesando tema {tema['id']}: {e}")
            continue

    print("\n🎉 PROCESO COMPLETADO")


if __name__ == "__main__":
    main()
