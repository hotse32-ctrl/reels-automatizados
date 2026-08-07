import os
import re
import sys
import json
import time
import random
import asyncio
import unicodedata
import argparse
import tempfile
from pathlib import Path

import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont

if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

from moviepy.editor import (
    VideoFileClip, ImageClip, CompositeVideoClip, CompositeAudioClip,
    AudioFileClip, concatenate_videoclips, concatenate_audioclips
)
from moviepy.audio.fx.all import audio_loop, volumex
from moviepy.audio.AudioClip import AudioClip
import moviepy.video.fx.all as vfx

import edge_tts
import google.generativeai as genai

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FB_ACCESS_TOKEN = os.environ.get("FACEBOOK_ACCESS_TOKEN")
PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID")
YOUTUBE_TOKEN_JSON = os.environ.get("YOUTUBE_TOKEN_JSON")
GOOGLE_DRIVE_TOKEN_JSON = os.environ.get("GOOGLE_DRIVE_TOKEN_JSON")

IG_USER_ID = os.environ.get("INSTAGRAM_BUSINESS_ID", "17841443907833300")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY")
THREADS_ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN")

W, H = 720, 1280
FPS = 24
VIDEO_BASE_PATH = "assets/video_base.mp4"

DRIVE_FOLDER_ID_IMAGENES = "1jJoLkmhkOqjUN-uQCn4J0RTPPzptZwwX"
ZOOM_FINAL_IMAGEN = 1.15

DRIVE_FOLDER_ID_VIDEOS = "1cjjDY5KIxaqy31iS3mJtsbGgN6C1pg9h"
DRIVE_FOLDER_ID_VIDEOS_GENERADOS = "1WhNSgQm2AEB3AQ8gpyMRq3RoQGCYcUF1"
DRIVE_FOLDER_ID_TEXTO = "1k-GK0WjkM-uItpt25yAZXWPn3wF4M8KZ"

TEMA_CARPETA_TEXTO_ID = {
    1: "1zVj4irQcY3IpgBQ2ssmZ5JolzXQeMNi5",
    2: "1E8_R9kZTbZwnlB4WipOUh2oUOZTtyt2z",
    3: "1Le07h9JVFQGngj8o8Ol__GAOUBHka1FY",
    4: "1sNx-2p-U7kdcojI9jD9psU_45LgP5nTJ",
    5: "1FmCgRHfpFXx9EgKqiBlYx_RY9-gE_UNl",
    6: "1Kd2Uxa74LgGNf1MtpmrGWdFYX9XTQ2aR",
    7: "1tjimTuIdXwCm-GjkU4j99tBK1_U435eu",
    8: "1eyL_Fuu_INBXKzkqGM4bgQXr4G_lvpvz",
    9: "18Ik3zp9UlkeQBgNg1SClIbLM2_6vPRy6",
    10: "17_tUjp0YLafbeCLs2rwI7JFXT_-UumGf",
}

VOZ_TTS = "es-MX-JorgeNeural"

PAUSA_ENTRE_FRASES = 0.4
FADE_OUT = 0.15
FADE_IN = 0.15
HOLD_FINAL = 0.6
INTRO_SILENCIO = 0.0

FONT_SIZE = 60
MAX_ANCHO_TEXTO = int(W * 0.7)

COLOR_BLANCO = (255, 255, 255, 255)
COLOR_ROJO = (220, 0, 0, 255)
COLOR_SOMBRA = (0, 0, 0, 160)

CTA_TEXTO = "Sigueme para mas reels como este."
CTA_PALABRAS_CLAVE = ["sigueme"]
CTA_DURACION = 2.5
CTA_FADE_IN = 0.3

os.makedirs("output", exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="reels_media_"))

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
        "ejemplo_guion": "Desaparecio sin aviso. No hubo adios. Solo vacio. Te dejo con preguntas. Que hiciste mal? Nada. El problema no eras tu. Era su cobardia. No vuelvas a buscar quien no te busco.",
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


def quitar_ene(texto):
    return "ñ" not in texto.lower()


def normalizar_palabra(p):
    p = p.strip(".,;:!?¿¡\"'()")
    p = unicodedata.normalize("NFKD", p).encode("ascii", "ignore").decode("ascii")
    return p.lower()


def dividir_en_frases(guion):
    partes = [p.strip() for p in guion.split(".") if p.strip()]
    return [p + "." for p in partes]


ANGULOS_CREATIVOS = [
    "Empieza con una pregunta directa que incomode a quien lo escucha.",
    "Empieza describiendo una escena cotidiana y concreta.",
    "Usa como imagen central una comparacion con algo fisico o cotidiano.",
    "Empieza con una orden corta y directa, casi un mandato, y luego explica por que.",
    "Contrasta lo que la persona cree que es verdad con lo que en realidad esta pasando.",
    "Cuentalo como si describieras algo que paso anoche o hace poco, en pasado breve, y termina en presente.",
    "Usa una progresion de tres pasos (primero..., luego..., al final...) como estructura del guion.",
    "Empieza negando de golpe una creencia comun sobre el tema.",
    "Usa una metafora de la naturaleza (fuego, agua, tormenta, raices, cicatrices) como hilo conductor.",
    "Empieza con una afirmacion incomoda sobre quien escucha, casi acusatoria, y luego suaviza hacia la esperanza.",
]


def generar_guion(tema, model):
    angulo = random.choice(ANGULOS_CREATIVOS)

    prompt = (
        "Eres un guionista experto en contenido motivacional y de psicologia emocional "
        "para Reels/Shorts en espanol.\n\n"
        f"Tema del dia: \"{tema['nombre']}\"\n\n"
        "Escribe un guion de voz en off ORIGINAL de 60 a 75 palabras (nunca mas de 75), "
        "en segunda persona (\"tu\"), tono dramatico y reflexivo, con frases cortas "
        "separadas por puntos (como golpes de efecto).\n\n"
        "A continuacion hay un ejemplo, PERO es SOLO una referencia de tono, ritmo y "
        "extension, no una plantilla para reescribir con sinonimos. Esta terminantemente "
        "prohibido reutilizar las mismas palabras, frases, metaforas, ejemplos o "
        "estructura de frase de este ejemplo:\n\n"
        f"\"{tema['ejemplo_guion']}\"\n\n"
        f"ENFOQUE OBLIGATORIO PARA ESTE GUION EN PARTICULAR:\n{angulo}\n\n"
        "REGLAS OBLIGATORIAS:\n"
        "1. Entre 60 y 75 palabras en total (nunca mas de 75).\n"
        "2. Prohibido usar la letra ñ en cualquier palabra.\n"
        "3. Frases cortas, separadas por puntos.\n"
        "4. Espanol neutro, tono dramatico/reflexivo, segunda persona.\n"
        "5. Marca entre 5 y 7 palabras clave del guion.\n"
        "6. No copies ni parafrasees el ejemplo.\n\n"
        "Responde UNICAMENTE con un JSON valido, sin texto adicional, con este formato "
        "exacto:\n"
        '{"guion": "texto del guion aqui", "palabras_clave": ["palabra1", "palabra2", "palabra3"]}'
    )

    ultimo_error = None
    for intento in range(3):
        try:
            respuesta = model.generate_content(
                prompt,
                generation_config={"temperature": 1.3, "top_p": 0.95},
            )
            texto = respuesta.text.strip()
            texto = re.sub(r"^```json\s*|\s*```$", "", texto.strip(), flags=re.MULTILINE).strip()
            data = json.loads(texto)
            guion = data["guion"].strip()
            palabras_clave = [normalizar_palabra(p) for p in data.get("palabras_clave", [])]

            if not quitar_ene(guion):
                ultimo_error = "El guion generado contiene la letra enie"
                print(f"Intento {intento+1}: {ultimo_error}, reintentando...")
                continue

            num_palabras = len(guion.split())
            if num_palabras < 60 or num_palabras > 75:
                ultimo_error = f"Largo fuera de rango ({num_palabras} palabras)"
                print(f"Intento {intento+1}: {ultimo_error}, reintentando...")
                continue

            print(f"Guion generado para tema '{tema['nombre']}' ({num_palabras} palabras)")
            return guion, palabras_clave

        except Exception as e:
            ultimo_error = str(e)
            print(f"Intento {intento+1} fallo al generar guion: {e}")

    print(f"No se pudo generar guion valido tras 3 intentos ({ultimo_error}). Usando guion de ejemplo de respaldo.")
    return tema["ejemplo_guion"], tema["ejemplo_keywords"]


def generar_audio_frase(texto_frase, ruta_salida):
    try:
        async def _generar():
            communicate = edge_tts.Communicate(texto_frase, voice=VOZ_TTS)
            await communicate.save(ruta_salida)

        asyncio.run(_generar())
        clip = AudioFileClip(ruta_salida)
        duracion = clip.duration
        clip.close()
        return duracion
    except Exception as e:
        print(f"Error al generar audio de la frase '{texto_frase[:30]}...': {e}")
        return None


def descargar_sonido_ambiental(url, ruta_salida):
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        with open(ruta_salida, "wb") as f:
            f.write(r.content)
        print("Sonido ambiental descargado")
        return True
    except Exception as e:
        print(f"Error al descargar sonido ambiental: {e}")
        return False


def obtener_fuente(tamano):
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
            print("Fuente Montserrat (variable) descargada")
        except Exception as e:
            print(f"No se pudo descargar Montserrat: {e}")

    if os.path.exists(ruta_descarga):
        font = ImageFont.truetype(ruta_descarga, tamano)
        try:
            font.set_variation_by_axes([700])
            print("Peso Bold (700) aplicado a Montserrat")
        except Exception as e:
            print(f"No se pudo fijar el peso Bold de la fuente variable: {e}")
        return font

    for c in [
        "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]:
        if os.path.exists(c):
            print(f"Usando fuente de respaldo: {c}")
            return ImageFont.truetype(c, tamano)

    return ImageFont.load_default()


def envolver_en_lineas(palabras, font, draw, max_ancho):
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
    if linea_actual:
        lineas.append(linea_actual)
    return lineas


def renderizar_estado(lineas_completas, num_palabras_visibles, palabras_clave, font):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    todas_palabras = [p for linea in lineas_completas for p in linea]
    visibles = todas_palabras[:num_palabras_visibles]

    idx = 0
    lineas_render = []
    for linea in lineas_completas:
        n = len(linea)
        vis_en_linea = visibles[idx:idx + n]
        lineas_render.append(vis_en_linea)
        idx += n

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
            draw.text((x + 3, y + 3), palabra, font=font, fill=COLOR_SOMBRA)
            draw.text((x, y), palabra, font=font, fill=color)
            x += draw.textlength(palabra + " ", font=font)
        y += alto_linea

    return img


def construir_clip_frase(frase, duracion_frase, palabras_clave, font, draw_dummy, img_dummy):
    palabras = frase.split()
    lineas = envolver_en_lineas(palabras, font, draw_dummy, MAX_ANCHO_TEXTO)
    total_palabras = sum(len(l) for l in lineas)

    pesos = [max(len(normalizar_palabra(p)), 1) for l in lineas for p in l]
    peso_total = sum(pesos)

    clips = []
    for n in range(1, total_palabras + 1):
        img = renderizar_estado(lineas, n, palabras_clave, font)
        duracion = duracion_frase * (pesos[n - 1] / peso_total)
        clips.append(ImageClip(np.array(img)).set_duration(duracion))

    return concatenate_videoclips(clips, method="compose")


def construir_audio_y_subtitulos(guion, palabras_clave, font):
    frases = dividir_en_frases(guion)
    img_dummy = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_dummy = ImageDraw.Draw(img_dummy)

    clips_audio = []
    clips_subs = []

    if INTRO_SILENCIO > 0:
        clips_audio.append(AudioClip(lambda t: [0, 0], duration=INTRO_SILENCIO))
        clips_subs.append(ImageClip(np.array(img_dummy)).set_duration(INTRO_SILENCIO))

    for i, frase in enumerate(frases):
        ruta_frase = f"output/frase_{i}.mp3"
        duracion_frase = generar_audio_frase(frase, ruta_frase)

        if duracion_frase is None:
            n_palabras = len(frase.split())
            duracion_frase = max(n_palabras * 0.35, 0.5)
            audio_frase = AudioClip(lambda t: [0, 0], duration=duracion_frase)
        else:
            audio_frase = AudioFileClip(ruta_frase)

        clips_audio.append(audio_frase)
        clip_frase = construir_clip_frase(frase, duracion_frase, palabras_clave, font, draw_dummy, img_dummy)

        es_ultima = (i == len(frases) - 1)
        if not es_ultima:
            clip_frase = clip_frase.crossfadeout(FADE_OUT)
        else:
            ultimo_estado = renderizar_estado(
                envolver_en_lineas(frase.split(), font, draw_dummy, MAX_ANCHO_TEXTO),
                len(frase.split()), palabras_clave, font
            )
            hold = ImageClip(np.array(ultimo_estado)).set_duration(HOLD_FINAL)
            clip_frase = concatenate_videoclips([clip_frase, hold], method="compose")

        if i > 0:
            clip_frase = clip_frase.crossfadein(FADE_IN)

        clips_subs.append(clip_frase)

        if not es_ultima:
            silencio = AudioClip(lambda t: [0, 0], duration=PAUSA_ENTRE_FRASES)
            clips_audio.append(silencio)
            blanco = ImageClip(np.array(img_dummy)).set_duration(PAUSA_ENTRE_FRASES)
            clips_subs.append(blanco)

    audio_final = concatenate_audioclips(clips_audio)
    subs_final = concatenate_videoclips(clips_subs, method="compose")
    return audio_final, subs_final, audio_final.duration


def obtener_credenciales_drive():
    if not GOOGLE_DRIVE_TOKEN_JSON:
        return None
    try:
        with open("drive_token.json", "w") as f:
            f.write(GOOGLE_DRIVE_TOKEN_JSON)
        creds = Credentials.from_authorized_user_file(
            "drive_token.json",
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        print(f"No se pudieron cargar las credenciales de Drive: {e}")
        return None


def obtener_o_crear_subcarpeta(drive_service, parent_id, nombre):
    query = (
        f"'{parent_id}' in parents and trashed = false "
        f"and mimeType = 'application/vnd.google-apps.folder' and name = '{nombre}'"
    )
    resultado = drive_service.files().list(q=query, fields="files(id, name)").execute()
    encontradas = resultado.get("files", [])
    if encontradas:
        return encontradas[0]["id"]

    metadata = {
        "name": nombre,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    carpeta = drive_service.files().create(body=metadata, fields="id").execute()
    print(f"Subcarpeta '{nombre}' creada en Drive.")
    return carpeta["id"]


def listar_archivos_texto_carpeta(drive_service, carpeta_id):
    query = (
        f"'{carpeta_id}' in parents and trashed = false "
        "and mimeType != 'application/vnd.google-apps.folder'"
    )
    resultado = drive_service.files().list(
        q=query, fields="files(id, name, mimeType)", pageSize=1000
    ).execute()
    return resultado.get("files", [])


def _clave_numero_archivo(archivo):
    nombre = os.path.splitext(archivo["name"])[0].strip()
    try:
        return int(nombre)
    except ValueError:
        return 10**9


def descargar_texto_archivo(drive_service, archivo):
    file_id = archivo["id"]
    mime = archivo.get("mimeType", "")
    try:
        if mime == "application/vnd.google-apps.document":
            data = drive_service.files().export(fileId=file_id, mimeType="text/plain").execute()
            texto = data.decode("utf-8") if isinstance(data, bytes) else data
            return texto.strip()

        ruta_local = TMP_DIR / f"frase_{file_id}"
        request = drive_service.files().get_media(fileId=file_id)
        with open(ruta_local, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            listo = False
            while not listo:
                _, listo = downloader.next_chunk()

        if mime == "text/plain" or archivo["name"].lower().endswith(".txt"):
            with open(ruta_local, "r", encoding="utf-8", errors="ignore") as f:
                return f.read().strip()

        import docx
        documento = docx.Document(str(ruta_local))
        texto = "\n".join(p.text for p in documento.paragraphs if p.text.strip())
        return texto.strip()
    except Exception as e:
        print(f"No se pudo leer el archivo '{archivo.get('name')}' de Drive: {e}")
        return None


def mover_archivo_drive(drive_service, file_id, carpeta_origen, carpeta_destino):
    try:
        drive_service.files().update(
            fileId=file_id, addParents=carpeta_destino, removeParents=carpeta_origen,
            fields="id, parents",
        ).execute()
        return True
    except Exception as e:
        print(f"No se pudo mover el archivo en Drive: {e}")
        return False


def obtener_guion_tema(tema, drive_service):
    carpeta_tema_id = TEMA_CARPETA_TEXTO_ID.get(tema["id"])

    if drive_service is None or not carpeta_tema_id:
        print("Drive no disponible para leer frases: usando guion de ejemplo de respaldo.")
        return tema["ejemplo_guion"], []

    try:
        carpeta_usada_id = obtener_o_crear_subcarpeta(drive_service, carpeta_tema_id, "Usada")
        carpeta_reutilizada_id = obtener_o_crear_subcarpeta(drive_service, carpeta_tema_id, "Reutilizada")

        nuevas = listar_archivos_texto_carpeta(drive_service, carpeta_tema_id)
        if nuevas:
            elegido = min(nuevas, key=_clave_numero_archivo)
            texto = descargar_texto_archivo(drive_service, elegido)
            if texto:
                mover_archivo_drive(drive_service, elegido["id"], carpeta_tema_id, carpeta_usada_id)
                print(f"Frase nueva usada para '{tema['nombre']}': archivo '{elegido['name']}'")
                return texto, []
            print(f"No se pudo leer el archivo elegido ('{elegido['name']}'), se intenta con 'Usada'.")

        usadas = listar_archivos_texto_carpeta(drive_service, carpeta_usada_id)
        if usadas:
            elegido = min(usadas, key=_clave_numero_archivo)
            texto = descargar_texto_archivo(drive_service, elegido)
            if texto:
                mover_archivo_drive(drive_service, elegido["id"], carpeta_usada_id, carpeta_reutilizada_id)
                print(f"Sin frases nuevas para '{tema['nombre']}': se reutilizo el archivo '{elegido['name']}'")
                return texto, []

        print(f"No hay frases nuevas ni reutilizables en Drive para '{tema['nombre']}'. Usando guion de ejemplo de respaldo.")
        return tema["ejemplo_guion"], []

    except Exception as e:
        print(f"Error leyendo el banco de frases en Drive: {e}. Usando guion de ejemplo de respaldo.")
        return tema["ejemplo_guion"], []


def listar_media_drive(drive_service, carpeta_id, tipo_mime):
    try:
        query = (
            f"'{carpeta_id}' in parents and trashed = false "
            f"and (mimeType contains '{tipo_mime}')"
        )
        resultado = drive_service.files().list(
            q=query, fields="files(id, name)", pageSize=1000
        ).execute()
        return resultado.get("files", [])
    except Exception as e:
        print(f"No se pudo listar la carpeta de Drive: {e}")
        return []


def descargar_archivo_drive(drive_service, file_id, nombre):
    try:
        ruta_local = TMP_DIR / nombre
        request = drive_service.files().get_media(fileId=file_id)
        with open(ruta_local, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            listo = False
            while not listo:
                _, listo = downloader.next_chunk()
        return str(ruta_local)
    except Exception as e:
        print(f"No se pudo descargar '{nombre}' de Drive: {e}")
        return None


def elegir_video_aleatorio_drive(drive_service):
    if drive_service is None:
        return None
    videos = listar_media_drive(drive_service, DRIVE_FOLDER_ID_VIDEOS, "video/")
    if not videos:
        return None
    elegido = random.choice(videos)
    print(f"Video de fondo elegido al azar: {elegido['name']}")
    return descargar_archivo_drive(drive_service, elegido["id"], elegido["name"])


def elegir_imagen_aleatoria_drive(drive_service):
    if drive_service is None:
        return None
    imagenes = listar_media_drive(drive_service, DRIVE_FOLDER_ID_IMAGENES, "image/")
    if not imagenes:
        print("El banco de imagenes en Drive esta vacio o no se pudo leer.")
        return None
    elegida = random.choice(imagenes)
    print(f"Imagen de fondo elegida del banco de Drive: {elegida['name']}")
    return descargar_archivo_drive(drive_service, elegida["id"], elegida["name"])


def crear_clip_fondo_imagen(ruta_imagen, duracion):
    base = ImageClip(ruta_imagen).set_duration(duracion)
    escala_cobertura = max(W / base.w, H / base.h)
    base = base.resize(escala_cobertura)

    base = base.fx(
        vfx.resize,
        lambda t: 1 + (ZOOM_FINAL_IMAGEN - 1) * (t / duracion) if duracion > 0 else 1,
    )
    base = base.set_position(("center", "center"))
    return CompositeVideoClip([base], size=(W, H)).set_duration(duracion)


def crear_clip_fondo_video(ruta_video, duracion):
    clip = VideoFileClip(ruta_video).without_audio()

    escala_cobertura = max(W / clip.w, H / clip.h)
    clip = clip.resize(escala_cobertura)
    clip = vfx.crop(
        clip, width=W, height=H,
        x_center=clip.w / 2, y_center=clip.h / 2,
    )

    if clip.duration < duracion:
        n_loops = int(duracion // clip.duration) + 1
        clip = concatenate_videoclips([clip] * n_loops)
    clip = clip.subclip(0, duracion)
    clip = clip.set_position(("center", "center"))
    return CompositeVideoClip([clip], size=(W, H)).set_duration(duracion)


def subir_video_a_drive(drive_service, ruta_video, nombre):
    if drive_service is None:
        return
    try:
        metadata = {"name": nombre, "parents": [DRIVE_FOLDER_ID_VIDEOS_GENERADOS]}
        media = MediaFileUpload(ruta_video, resumable=True)
        drive_service.files().create(body=metadata, media_body=media, fields="id").execute()
        print(f"Copia del video subida a Drive (Videos Generados): {nombre}")
    except Exception as e:
        print(f"No se pudo subir la copia del video a Drive: {e}")


def construir_video_tema(tema, guion, palabras_clave, ruta_salida, drive_service):
    font = obtener_fuente(FONT_SIZE)

    print("Generando audio y subtitulos sincronizados (frase por frase)...")
    audio_narracion, clip_subtitulos, duracion_narracion = construir_audio_y_subtitulos(guion, palabras_clave, font)
    duracion_subs = clip_subtitulos.duration
    print(f"   Duracion real del audio: {duracion_narracion:.1f}s (subtitulos: {duracion_subs:.1f}s)")

    img_dummy = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_dummy = ImageDraw.Draw(img_dummy)
    cta_lineas = envolver_en_lineas(CTA_TEXTO.split(), font, draw_dummy, MAX_ANCHO_TEXTO)
    cta_img = renderizar_estado(cta_lineas, sum(len(l) for l in cta_lineas), CTA_PALABRAS_CLAVE, font)
    cta_clip = ImageClip(np.array(cta_img)).set_duration(CTA_DURACION).crossfadein(CTA_FADE_IN)
    clip_subtitulos = concatenate_videoclips([clip_subtitulos, cta_clip], method="compose")

    duracion_total = clip_subtitulos.duration
    print(f"   Duracion total con CTA final: {duracion_total:.1f}s")

    print("Preparando fondo (1. video al azar, 2. imagen al azar, 3. video base)...")
    ruta_video = elegir_video_aleatorio_drive(drive_service)
    if ruta_video:
        try:
            video_loop = crear_clip_fondo_video(ruta_video, duracion_total)
        except Exception as e:
            print(f"No se pudo usar el video de fondo elegido ({e}), se intenta con imagen.")
            ruta_video = None

    if not ruta_video:
        ruta_imagen = elegir_imagen_aleatoria_drive(drive_service)
        if ruta_imagen:
            video_loop = crear_clip_fondo_imagen(ruta_imagen, duracion_total)
        else:
            print("Sin video ni imagen de Drive disponibles, usando video base en loop.")
            video_original = VideoFileClip(VIDEO_BASE_PATH).resize((W, H))
            n_loops = int(duracion_total // video_original.duration) + 1
            video_loop = concatenate_videoclips([video_original] * n_loops).subclip(0, duracion_total)

    if audio_narracion.duration < duracion_total:
        silencio = AudioClip(lambda t: [0, 0], duration=duracion_total - audio_narracion.duration)
        audio_narracion = concatenate_audioclips([audio_narracion, silencio])

    ruta_sonido = "output/ambiente.mp3"
    audio_ambiente = None
    if descargar_sonido_ambiental(tema["sonido_url"], ruta_sonido):
        try:
            amb = AudioFileClip(ruta_sonido)
            amb = audio_loop(amb, duration=duracion_total)
            audio_ambiente = volumex(amb, 0.12)
        except Exception as e:
            print(f"No se pudo procesar el sonido ambiental: {e}")

    if audio_ambiente is not None:
        audio_final = CompositeAudioClip([audio_ambiente, volumex(audio_narracion, 1.0)])
    else:
        audio_final = audio_narracion

    audio_final = audio_final.set_duration(duracion_total)

    video_final = CompositeVideoClip([video_loop, clip_subtitulos.set_position(("center", "center"))])
    video_final = video_final.set_audio(audio_final).set_duration(duracion_total)

    video_final.write_videofile(
        ruta_salida, fps=FPS, codec="libx264", audio_codec="aac",
        threads=4, verbose=False, logger=None
    )
    print(f"Video final generado: {ruta_salida}")
    return duracion_total


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
            print("Publicado en Facebook:", resp.json())
        else:
            print(f"Error en Facebook: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Excepcion al publicar en Facebook: {e}")


def publicar_youtube(ruta_video, titulo, descripcion):
    try:
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
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
        }
        media = MediaFileUpload(ruta_video, chunksize=-1, resumable=True)
        req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        resp = req.execute()
        print("Publicado en YouTube:", resp["id"], f"https://youtu.be/{resp['id']}")
    except Exception as e:
        print(f"Error al publicar en YouTube: {e}")


def subir_video_temporal_github(ruta_video, nombre_archivo):
    if not GITHUB_TOKEN or not GITHUB_REPOSITORY:
        raise Exception("Falta GITHUB_TOKEN o GITHUB_REPOSITORY (solo disponibles al correr dentro de GitHub Actions)")

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    tag = f"tmp-video-{int(time.time())}"
    resp = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases",
        headers=headers,
        json={
            "tag_name": tag,
            "name": "Video temporal (auto, para publicar en Instagram/Threads)",
            "body": "Release temporal creado automaticamente por generar_reel_v2.py solo para darle una URL publica al video antes de publicarlo. Se borra automaticamente apenas termina.",
            "draft": False,
            "prerelease": True,
        },
        timeout=30,
    )
    resp.raise_for_status()
    release = resp.json()
    release_id = release["id"]
    upload_url = release["upload_url"].split("{")[0]

    with open(ruta_video, "rb") as f:
        video_bytes = f.read()

    resp2 = requests.post(
        f"{upload_url}?name={nombre_archivo}",
        headers={**headers, "Content-Type": "video/mp4"},
        data=video_bytes,
        timeout=180,
    )
    resp2.raise_for_status()
    asset = resp2.json()
    print(f"Video subido a release temporal de GitHub: {asset['browser_download_url']}")
    return release_id, tag, asset["browser_download_url"]


def borrar_release_temporal(release_id, tag):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    try:
        requests.delete(f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/{release_id}", headers=headers, timeout=30)
        requests.delete(f"https://api.github.com/repos/{GITHUB_REPOSITORY}/git/refs/tags/{tag}", headers=headers, timeout=30)
        print("Release temporal borrado")
    except Exception as e:
        print(f"No se pudo borrar el release temporal (no es grave, solo queda como basura en el repo): {e}")


def _publicar_contenedor_instagram(video_url, media_type, caption=None):
    url_contenedor = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
    data = {
        "media_type": media_type,
        "video_url": video_url,
        "access_token": FB_ACCESS_TOKEN,
    }
    if caption and media_type != "STORIES":
        data["caption"] = caption

    resp = requests.post(url_contenedor, data=data, timeout=60)
    if not resp.ok:
        raise Exception(f"Instagram rechazo la creacion del contenedor ({resp.status_code}): {resp.text}")
    contenedor_id = resp.json()["id"]

    url_estado = f"https://graph.facebook.com/v19.0/{contenedor_id}"
    estado = None
    for _ in range(30):
        time.sleep(10)
        r = requests.get(url_estado, params={"fields": "status_code", "access_token": FB_ACCESS_TOKEN}, timeout=30)
        estado = r.json().get("status_code")
        print(f"   [{media_type}] Estado del contenedor de Instagram: {estado}")
        if estado == "FINISHED":
            break
        if estado == "ERROR":
            raise Exception("El procesamiento del video en Instagram termino en estado ERROR")

    if estado != "FINISHED":
        raise Exception(f"Timeout esperando que Instagram procese el video (ultimo estado: {estado})")

    url_publicar = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
    resp2 = requests.post(url_publicar, data={"creation_id": contenedor_id, "access_token": FB_ACCESS_TOKEN}, timeout=60)
    if not resp2.ok:
        raise Exception(f"Instagram rechazo la publicacion del contenedor ({resp2.status_code}): {resp2.text}")
    print(f"Publicado en Instagram ({media_type}):", resp2.json())


def publicar_instagram_todo(ruta_video, titulo, descripcion):
    if not IG_USER_ID:
        print("IG_USER_ID no configurado, se omite publicacion en Instagram.")
        return

    release_id = None
    tag = None
    try:
        nombre_archivo = os.path.basename(ruta_video)
        print("Subiendo video a almacenamiento temporal (GitHub Release) para Instagram...")
        release_id, tag, video_url = subir_video_temporal_github(ruta_video, nombre_archivo)

        caption = f"{titulo}\n\n{descripcion}\n\n#motivacion #superacion #reflexion #psicologia"
        _publicar_contenedor_instagram(video_url, "REELS", caption=caption)
        _publicar_contenedor_instagram(video_url, "STORIES")

    except Exception as e:
        print(f"Error al publicar en Instagram: {e}")
    finally:
        if release_id:
            borrar_release_temporal(release_id, tag)


def publicar_threads(ruta_video, titulo, descripcion):
    if not THREADS_ACCESS_TOKEN:
        print("THREADS_ACCESS_TOKEN no configurado, se omite publicacion en Threads.")
        return

    release_id = None
    tag = None
    try:
        nombre_archivo = os.path.basename(ruta_video)
        print("Subiendo video a almacenamiento temporal (GitHub Release) para Threads...")
        release_id, tag, video_url = subir_video_temporal_github(ruta_video, nombre_archivo)

        texto = f"{titulo}\n\n{descripcion}"[:500]

        url_contenedor = "https://graph.threads.net/v1.0/me/threads"
        resp = requests.post(url_contenedor, data={
            "media_type": "VIDEO",
            "video_url": video_url,
            "text": texto,
            "access_token": THREADS_ACCESS_TOKEN,
        }, timeout=60)
        resp.raise_for_status()
        contenedor_id = resp.json()["id"]

        url_estado = f"https://graph.threads.net/v1.0/{contenedor_id}"
        estado = None
        for _ in range(30):
            time.sleep(10)
            r = requests.get(url_estado, params={"fields": "status", "access_token": THREADS_ACCESS_TOKEN}, timeout=30)
            estado = r.json().get("status")
            print(f"   [THREADS] Estado del contenedor: {estado}")
            if estado == "FINISHED":
                break
            if estado == "ERROR":
                raise Exception("El procesamiento del video en Threads termino en estado ERROR")

        if estado != "FINISHED":
            raise Exception(f"Timeout esperando que Threads procese el video (ultimo estado: {estado})")

        url_publicar = "https://graph.threads.net/v1.0/me/threads_publish"
        resp2 = requests.post(url_publicar, data={"creation_id": contenedor_id, "access_token": THREADS_ACCESS_TOKEN}, timeout=60)
        resp2.raise_for_status()
        print("Publicado en Threads:", resp2.json())

    except Exception as e:
        print(f"Error al publicar en Threads: {e}")
    finally:
        if release_id:
            borrar_release_temporal(release_id, tag)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tema", type=int, default=None, help="ID de un solo tema a procesar (1-10). Si se omite, procesa los 10.")
    parser.add_argument("--no-publicar", action="store_true", help="Genera el video pero no publica (para pruebas).")
    args = parser.parse_args()

    drive_service = obtener_credenciales_drive()
    if drive_service is None:
        print("GOOGLE_DRIVE_TOKEN_JSON no configurado o invalido: se usaran los respaldos locales (guion de ejemplo y video base).")

    temas_a_procesar = [t for t in TEMAS if t["id"] == args.tema] if args.tema else TEMAS

    for tema in temas_a_procesar:
        print(f"\n========== TEMA {tema['id']}: {tema['nombre']} ==========")
        try:
            guion, palabras_clave = obtener_guion_tema(tema, drive_service)
            ruta_salida = f"output/reel_tema{tema['id']}.mp4"
            construir_video_tema(tema, guion, palabras_clave, ruta_salida, drive_service)

            if not args.no_publicar:
                titulo = tema["nombre"]
                descripcion = guion
                publicar_youtube(ruta_salida, titulo, descripcion)
                publicar_instagram_todo(ruta_salida, titulo, descripcion)
                publicar_threads(ruta_salida, titulo, descripcion)
                nombre_drive = f"tema{tema['id']}_{re.sub(r'[^a-zA-Z0-9]+', '_', tema['nombre'])}.mp4"
                subir_video_a_drive(drive_service, ruta_salida, nombre_drive)
            else:
                print("--no-publicar activado, video generado pero no publicado.")

        except Exception as e:
            print(f"Error procesando tema {tema['id']}: {e}")
            continue

    print("\nPROCESO COMPLETADO")


if __name__ == "__main__":
    main()
