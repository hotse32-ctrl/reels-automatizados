import os
import re
import sys
import json
import time
import random
import asyncio
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

import edge_tts
import google.generativeai as genai

from banco_guiones import BANCO_GUIONES

# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FB_ACCESS_TOKEN = os.environ.get("FACEBOOK_ACCESS_TOKEN")
PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID")
YOUTUBE_TOKEN_JSON = os.environ.get("YOUTUBE_TOKEN_JSON")

# Instagram: publica usando el mismo token de la Página de Facebook (ya
# vinculada a la cuenta de Instagram Business/Creator @curiosidades._ia).
# El ID de abajo es el de esa cuenta, confirmado por la Graph API el 19 jul
# 2026. Se puede sobreescribir con el secreto INSTAGRAM_BUSINESS_ID si algún
# día cambia la cuenta vinculada, sin tener que tocar el código.
IG_USER_ID = os.environ.get("INSTAGRAM_BUSINESS_ID", "17841443907833300")

# GitHub Actions inyecta esto automáticamente en cada ejecución — se usa
# solo para subir el video a un Release TEMPORAL (ver publicar_instagram_todo)
# y así darle a la API de Instagram una URL pública de la que pueda
# descargar el video (su Content Publishing API no acepta subida directa
# de archivo como sí hace Facebook).
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY")

# Threads: token de larga duración (60 días) generado como Threads Tester
# de la app "Reels Automatizados IA" en modo desarrollo (no requiere
# revisión de Meta porque solo publica en esta misma cuenta). OJO: a
# diferencia del token de Página de Facebook, este SÍ caduca a los 60 días
# y hay que regenerarlo a mano periódicamente (ver credenciales_reels.md).
THREADS_ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN")

W, H = 720, 1280
FPS = 24
VIDEO_BASE_PATH = "assets/video_base.mp4"

# --- Imagen de fondo fija por tema (con zoom lento tipo Ken Burns) ---
# Reemplaza al video base único: cada tema tiene su propia imagen fija
# (generada por Jose, guardada en assets/imagenes/temaN.jpg), y se le aplica
# un zoom lento continuo durante toda la duración del reel para que el
# fondo no se vea estático. ZOOM_FACTOR = cuánto más grande termina la
# imagen al final del video respecto al inicio (1.15 = 15% de zoom total).
CARPETA_IMAGENES_TEMA = "assets/imagenes"
ZOOM_FACTOR = 1.15

# Voz de edge-tts (voces neuronales de Microsoft, gratis, sin API key).
# es-MX-JorgeNeural: voz masculina, español latino, tono serio/profundo,
# encaja con el estilo dramático/reflexivo en segunda persona del guion.
# Reemplaza a gTTS (voz robótica tipo Google Translate) — decisión de Jose
# tras confirmar que la sincronización y el resto del video ya quedaron bien.
VOZ_TTS = "es-MX-JorgeNeural"


# --- Sincronización de subtítulos con la voz ---
# El audio se genera FRASE POR FRASE (no todo el guion en un solo llamado al
# motor de voz). Así se conoce la duración REAL y exacta de cada frase hablada,
# y las palabras en pantalla se reparten dentro de ese tiempo exacto — sync
# perfecto por diseño, sin necesidad de calcular ni adivinar ritmos de habla.
#
# El motor de voz no deja pausas de 1.5s entre frases como se pensó
# originalmente (deja pausas naturales cortas e irregulares); por eso el
# silencio ENTRE frases lo insertamos nosotros mismos, de forma controlada
# y exacta — esto sigue aplicando igual con edge-tts.
PAUSA_ENTRE_FRASES = 0.4   # segundos de silencio real insertado entre frases (en el audio Y en los subtítulos)
FADE_OUT = 0.15            # fundido de salida, dentro del propio tiempo de la frase que termina (no suma duración)
FADE_IN = 0.15             # fundido de entrada, dentro del propio tiempo de la frase que empieza (no suma duración)
HOLD_FINAL = 0.6           # segundos que se mantiene visible la última frase al terminar

FONT_SIZE = 60
MAX_ANCHO_TEXTO = int(W * 0.7)  # 70% del ancho, según especificación

COLOR_BLANCO = (255, 255, 255, 255)
COLOR_ROJO = (220, 0, 0, 255)
COLOR_SOMBRA = (0, 0, 0, 160)

# --- CTA final (llamado a seguir la cuenta) ---
# Se muestra al final de cada video, después de que termina el guion, con la
# palabra "Sigueme" en rojo (mismo estilo visual que las palabras clave) para
# que destaque. No lleva voz — se muestra en silencio (con el sonido ambiental
# de fondo todavía sonando) durante CTA_DURACION segundos, con un fundido de
# entrada. Pedido explícito de Jose para fomentar que sigan la cuenta.
CTA_TEXTO = "Sigueme para mas reels como este."
CTA_PALABRAS_CLAVE = ["sigueme"]
CTA_DURACION = 2.5
CTA_FADE_IN = 0.3

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
# ÁNGULOS CREATIVOS (se elige uno al azar en cada guion para forzar
# variedad real — sin esto, Gemini tiende a parafrasear el ejemplo con
# sinónimos en vez de inventar contenido nuevo, que fue justo el problema
# que detectó Jose al revisar el primer guion generado).
# ============================================================
ANGULOS_CREATIVOS = [
    "Empieza con una pregunta directa que incomode a quien lo escucha.",
    "Empieza describiendo una escena cotidiana y concreta (un mensaje que no llega, una llamada que no se hace, una puerta que se cierra).",
    "Usa como imagen central una comparación con algo físico o cotidiano (un objeto, un lugar, el clima, un sonido).",
    "Empieza con una orden corta y directa, casi un mandato, y luego explica por qué.",
    "Contrasta lo que la persona cree que es verdad con lo que en realidad está pasando.",
    "Cuéntalo como si describieras algo que pasó anoche o hace poco, en pasado breve, y termina en presente.",
    "Usa una progresión de tres pasos (primero..., luego..., al final...) como estructura del guion.",
    "Empieza negando de golpe una creencia común sobre el tema.",
    "Usa una metáfora de la naturaleza (fuego, agua, tormenta, raíces, cicatrices) como hilo conductor.",
    "Empieza con una afirmación incómoda sobre quien escucha, casi acusatoria, y luego suaviza hacia la esperanza.",
]

# ============================================================
# COMBINACIONES RETÓRICAS (se elige una al azar en cada guion, igual que
# el ángulo). Antes se exigían los 5 elementos SIEMPRE, lo que hacía que
# todos los guiones tuvieran la misma forma aunque el contenido cambiara.
# Cada combinación usa entre 3 y 5 de los 5 elementos, con una lógica de
# apertura/cuerpo/cierre coherente (no es una mezcla al azar) — algunas
# cierran con golpe directo (frase final puñetazo) y otras con un cierre
# más reflexivo, para variar también la FORMA, no solo las palabras.
# ============================================================
COMBINACIONES_RETORICAS = [
    "Usa PREGUNTA RETÓRICA (al inicio, para incomodar) + REPETICIÓN ECO (en el medio) + FRASE FINAL PUÑETAZO (para cerrar con golpe). No uses antítesis ni imagen potente en este guion.",
    "Usa ANTÍTESIS (al inicio, como contraste) + IMAGEN POTENTE (en el cuerpo) + FRASE FINAL PUÑETAZO (para cerrar con golpe). No uses pregunta retórica ni repetición eco en este guion.",
    "Usa IMAGEN POTENTE (al inicio) + REPETICIÓN ECO (en el cuerpo) + PREGUNTA RETÓRICA (como cierre, dejando pensando en vez de golpe directo). No uses antítesis ni frase final puñetazo en este guion.",
    "Usa REPETICIÓN ECO (desde el inicio) + ANTÍTESIS (en el cuerpo) + FRASE FINAL PUÑETAZO (para cerrar con golpe). No uses pregunta retórica ni imagen potente en este guion.",
    "Usa PREGUNTA RETÓRICA + ANTÍTESIS + IMAGEN POTENTE, en ese orden, con un cierre reflexivo y suave (SIN frase final puñetazo marcada, SIN repetición eco en este guion).",
    "Usa IMAGEN POTENTE (al inicio) + ANTÍTESIS (en el cuerpo) + FRASE FINAL PUÑETAZO (para cerrar con golpe). No uses pregunta retórica ni repetición eco en este guion.",
    "Usa REPETICIÓN ECO (al inicio) + PREGUNTA RETÓRICA (en el cuerpo) + FRASE FINAL PUÑETAZO (para cerrar con golpe). No uses antítesis ni imagen potente en este guion.",
    "Usa los 5 elementos completos: frase final puñetazo, pregunta retórica, antítesis, repetición eco, e imagen potente.",
    "Usa PREGUNTA RETÓRICA (al inicio) + REPETICIÓN ECO (en el cuerpo) + ANTÍTESIS + FRASE FINAL PUÑETAZO (para cerrar con golpe). No uses imagen potente en este guion.",
    "Usa ANTÍTESIS (al inicio) + REPETICIÓN ECO (en el cuerpo) + IMAGEN POTENTE, con un cierre reflexivo y suave (SIN frase final puñetazo marcada, SIN pregunta retórica en este guion).",
]


# ============================================================
# 1. GENERAR GUION CON GEMINI (por tema, con reglas estrictas)
# ============================================================
def generar_guion(tema, model):
    angulo = random.choice(ANGULOS_CREATIVOS)
    combinacion = random.choice(COMBINACIONES_RETORICAS)

    prompt = f"""Eres un guionista experto en contenido motivacional y de psicologia emocional para Reels/Shorts en español.

Tema del día: "{tema['nombre']}"

Escribe un texto para SUBTITULOS en pantalla de entre 66 y 70 palabras (nunca fuera de ese rango), en segunda persona ("tu"), tono dramático y reflexivo.

El texto debe sonar NATURAL, como una reflexión interna. NO uses punto tras cada frase corta. Combina frases cortas (4-6 palabras) con frases más largas (8-12 palabras). Usa comas y puntos seguidos para dar fluidez. El punto solo va al final de una idea completa.

ELEMENTOS OBLIGATORIOS (los 5 que hacen que el texto "retumbe"):
1. FRASE FINAL PUÑETAZO: Termina con una frase corta, contundente e inesperada. Que el espectador quiera repetirla en voz alta. Ejemplo: "El silencio no te protege, te entrega."
2. PREGUNTA RETÓRICA: Incluye al menos UNA pregunta que incomode al espectador. Ejemplo: "¿Hasta cuando vas a esperar a quien nunca llamo?"
3. ANTÍTESIS: Crea un contraste entre dos ideas opuestas en una misma frase. Ejemplo: "Te dice que te ama, pero te borra."
4. REPETICIÓN ECO: Repite una palabra clave 2 o 3 veces a lo largo del guion, como un latido. Ejemplo: "Esperaste. Esperaste que cambiara. Esperaste que te viera."
5. IMAGEN POTENTE: Usa una imagen tan visual que el espectador pueda "verla" con los ojos cerrados. Ejemplo: "Te dio un puñado de migajas y tu construiste un castillo con ellas."

EJEMPLO de ritmo natural con los 5 elementos aplicados (de otro tema, NO copies nada de esto):
"El reloj no se detiene, pero tu si. Te quedaste en la misma hora, esperando que el tiempo vuelva atras. ¿No ves que el mundo sigue sin ti? El miedo te ancla, pero la decision te suelta. No es que no puedas avanzar, es que te acostumbraste a esperar. Deja de esperar. El tiempo no vuelve, pero tu si puedes."

A continuación hay un ejemplo del TEMA ACTUAL, PERO es SOLO una referencia de tono, ritmo y extensión — no una plantilla para reescribir con sinónimos.
Está TERMINANTEMENTE PROHIBIDO reutilizar las mismas palabras, frases, metáforas, ejemplos o estructura de frase de este ejemplo.
Tu guion debe sonar como una idea completamente distinta sobre el mismo tema, con tus propias imágenes y palabras:

"{tema['ejemplo_guion']}"

ENFOQUE OBLIGATORIO PARA ESTE GUION EN PARTICULAR (síguelo, es lo que lo hace distinto cada vez):
{angulo}

REGLAS OBLIGATORIAS:
1. Entre 66 y 70 palabras en total (cuéntalas una por una antes de responder).
2. PROHIBIDO usar la letra "Ñ" o "ñ" en cualquier palabra, sin excepción. Evita por completo palabras como "año", "pequeño", "señal", "compañía" — reemplázalas por sinónimos SIN ñ que mantengan el significado correcto (ej: "pequeño" → "chico", "señal" → "muestra", "compañía" → "presencia", "año" → "ciclo" o reformula la frase). IMPORTANTE: nunca le quites la ñ a una palabra dejándola mal escrita (por ejemplo, JAMÁS escribas "ano" en vez de "año" — son palabras completamente distintas y una de ellas es vulgar). Si no encuentras un sinónimo natural, reformula toda la frase para evitar esa palabra.
3. PROHIBIDO usar punto tras cada frase corta. Usa comas y puntos seguidos para dar fluidez natural. El punto solo va al final de una idea completa.
4. COMBINACIÓN RETÓRICA OBLIGATORIA PARA ESTE GUION (usa SOLO los elementos que se indican aquí, no agregues los que no se piden): {combinacion}
5. Marca entre 5 y 7 "palabras clave" del guion. Deben ser SUSTANTIVOS o VERBOS de acción (no adjetivos ni conectores). Deben aparecer en posiciones de impacto: inicio o final de frase, o en la repetición eco.
6. NO copies ni parafrasees el ejemplo del tema actual: ni sus palabras clave, ni sus metáforas, ni el orden de sus ideas. Debe ser contenido nuevo.

Responde ÚNICAMENTE con un JSON válido, sin texto adicional, con este formato exacto:
{{"guion": "texto del guion aqui", "palabras_clave": ["palabra1", "palabra2", "palabra3"]}}
"""

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
                ultimo_error = "El guion generado contiene la letra Ñ"
                print(f"⚠️ Intento {intento+1}: {ultimo_error}, reintentando...")
                continue

            num_palabras = len(guion.split())
            if num_palabras < 66 or num_palabras > 70:
                ultimo_error = f"Largo fuera de rango ({num_palabras} palabras)"
                print(f"⚠️ Intento {intento+1}: {ultimo_error}, reintentando...")
                continue

            print(f"✅ Guion generado para tema '{tema['nombre']}' ({num_palabras} palabras, enfoque: {angulo[:40]}..., combinación: {combinacion[:40]}...)")
            print(f"   📝 {guion}")
            return guion, palabras_clave

        except Exception as e:
            ultimo_error = str(e)
            print(f"⚠️ Intento {intento+1} falló al generar guion: {e}")

    print(f"❌ No se pudo generar guion válido tras 3 intentos ({ultimo_error}). Usando guion de ejemplo de respaldo.")
    return tema["ejemplo_guion"], tema["ejemplo_keywords"]


# ============================================================
# 1.b BANCO DE GUIONES ESCRITO A MANO (fuente PRINCIPAL, ahorra cuota
# de Gemini). Gemini queda como RESPALDO, solo si el banco no tiene
# guiones para ese tema (nunca debería pasar, hay 45 por tema) o si
# hay algún error inesperado leyendo el banco.
# ============================================================
STOPWORDS_KEYWORDS = {
    "que", "para", "pero", "esa", "ese", "esta", "este", "esto", "eso",
    "como", "cuando", "donde", "aunque", "ahora", "hoy", "mismo", "misma",
    "tambien", "siempre", "nunca", "solo", "sola", "mas", "muy", "porque",
    "desde", "hasta", "entre", "sobre", "cada", "todo", "toda", "todos",
    "todas", "otra", "otro", "algo", "alguien", "nadie", "tiene", "tienes",
    "puede", "puedes", "hace", "haces", "vez", "asi", "sin", "con", "una",
    "uno", "unos", "unas", "los", "las", "del", "por", "sus", "tus", "mis",
}


def extraer_palabras_clave_banco(guion):
    """Los guiones escritos a mano en banco_guiones.py no traen una lista de
    palabras clave (a diferencia de los que genera Gemini con su propio JSON),
    así que se eligen automáticamente: palabras largas (>=6 letras), sin
    contar conectores/stopwords, priorizando variedad. Da un resultado
    aproximado pero suficiente para resaltar en rojo los términos de más
    peso visual del guion."""
    candidatas = []
    vistas = set()
    for palabra in guion.split():
        norm = normalizar_palabra(palabra)
        if len(norm) >= 6 and norm not in STOPWORDS_KEYWORDS and norm not in vistas:
            candidatas.append(norm)
            vistas.add(norm)
    return candidatas[:7] if candidatas else []


def obtener_guion_del_dia(tema, model):
    """Fuente PRINCIPAL de guiones: el banco escrito a mano (450 guiones,
    45 por tema, sin repetir hasta agotarlos). Se elige uno por día usando
    la fecha de Chile, rotando de forma determinística (mismo día = mismo
    guion, sin necesidad de guardar estado en ningún archivo). Cubre 45
    días seguidos sin llamar nunca a Gemini, alineado con el ciclo de
    renovación del token de Threads (~60 días).

    Si por algún motivo el banco no tiene guiones para este tema (no
    debería pasar), se usa Gemini como respaldo, igual que antes."""
    from datetime import datetime, timedelta, timezone
    banco_tema = BANCO_GUIONES.get(tema["id"])

    if banco_tema:
        offset_chile = timedelta(hours=-4)
        fecha_chile = (datetime.now(timezone.utc) + offset_chile).date()
        indice = fecha_chile.toordinal() % len(banco_tema)
        guion = banco_tema[indice]
        palabras_clave = extraer_palabras_clave_banco(guion)
        print(f"📚 Guion del banco para tema '{tema['nombre']}' (día {indice + 1}/{len(banco_tema)}): {guion[:60]}...")
        return guion, palabras_clave

    print(f"⚠️ No hay guiones en el banco para el tema {tema['id']}, usando Gemini como respaldo.")
    return generar_guion(tema, model)


# ============================================================
# 2. AUDIO DE NARRACIÓN (edge-tts neuronal, UNA LLAMADA POR FRASE)
# ============================================================
def generar_audio_frase(texto_frase, ruta_salida):
    """Genera el audio de UNA sola frase con edge-tts (voz neuronal de Microsoft,
    gratis y sin API key) y devuelve su duración real en segundos, o None si
    falla. Generar frase por frase (en vez de todo el guion junto) es lo que
    permite sincronizar los subtítulos EXACTO con la voz: se sabe con precisión
    cuánto dura hablada cada frase, sin tener que adivinar ritmos."""
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
        print(f"⚠️ Error al generar audio de la frase '{texto_frase[:30]}...': {e}")
        return None


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
def envolver_en_lineas(palabras, font, draw, max_ancho):
    """Distribuye la lista completa de palabras en tantas líneas como haga
    falta para que ninguna se salga del ancho máximo. SIN límite de líneas:
    si una frase es larga, se usan las líneas necesarias — nunca se descartan
    palabras (antes, con un tope fijo de 2 líneas, las palabras que sobraban
    simplemente desaparecían del video aunque la voz sí las decía)."""
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


def construir_clip_frase(frase, duracion_frase, palabras_clave, font, draw_dummy, img_dummy):
    """Construye el clip de subtítulo de UNA frase, revelando sus palabras
    dentro de exactamente `duracion_frase` segundos (la duración real de su
    audio). Cada palabra recibe tiempo proporcional a su largo en caracteres
    (una palabra larga tarda más en decirse que una corta), así que la suma
    de las palabras SIEMPRE calza exacto con lo que dura la voz diciendo
    esa frase — sync exacto, sin necesidad de fórmulas ni de adivinar ritmos."""
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
    """Genera el audio y los subtítulos animados JUNTOS, frase por frase, para
    que queden perfectamente sincronizados por construcción: cada frase se
    narra por separado con edge-tts (se conoce su duración real exacta), y el
    subtítulo de esa frase se reparte dentro de exactamente esa duración.
    Entre frases se inserta una pausa fija y corta (PAUSA_ENTRE_FRASES),
    la misma en el audio (silencio real) y en los subtítulos (fade-out +
    blanco + fade-in). Devuelve (audio_clip, subtitulos_clip, duracion_total)."""
    frases = dividir_en_frases(guion)
    img_dummy = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_dummy = ImageDraw.Draw(img_dummy)

    clips_audio = []
    clips_subs = []

    for i, frase in enumerate(frases):
        ruta_frase = f"output/frase_{i}.mp3"
        duracion_frase = generar_audio_frase(frase, ruta_frase)

        if duracion_frase is None:
            # Respaldo: si edge-tts falla en esta frase, estimamos un tiempo
            # razonable (0.35s por palabra) para no perder el video completo.
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
            # Mantener la última frase visible un poco más al terminar el audio
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
            # OJO: crossfadein()/crossfadeout() NO agregan duración extra en moviepy
            # (funden DENTRO del tiempo propio de cada clip). El único tiempo que se
            # suma de verdad al timeline es este clip en blanco — por eso debe durar
            # EXACTO lo mismo que el silencio insertado en el audio (PAUSA_ENTRE_FRASES),
            # si no, subtítulos y voz se desfasan cada vez más a medida que avanza el video.
            blanco = ImageClip(np.array(img_dummy)).set_duration(PAUSA_ENTRE_FRASES)
            clips_subs.append(blanco)

    audio_final = concatenate_audioclips(clips_audio)
    subs_final = concatenate_videoclips(clips_subs, method="compose")
    return audio_final, subs_final, audio_final.duration


def construir_clip_fondo_imagen(ruta_imagen, duracion):
    """Construye el fondo de un tema a partir de UNA imagen fija, con un
    zoom lento continuo (efecto Ken Burns) durante toda la duración del
    reel, para que no se vea estático. Primero se redimensiona la imagen
    para CUBRIR el lienzo 720x1280 (recortando el sobrante, sin barras
    negras), y luego se le aplica el zoom sobre ese tamaño ya ajustado."""
    imagen_base = ImageClip(ruta_imagen).set_duration(duracion)

    ratio_lienzo = W / H
    ratio_imagen = imagen_base.w / imagen_base.h
    if ratio_imagen > ratio_lienzo:
        imagen_base = imagen_base.resize(height=H)
    else:
        imagen_base = imagen_base.resize(width=W)

    def factor_zoom(t):
        return 1 + (ZOOM_FACTOR - 1) * (t / duracion)

    imagen_zoom = imagen_base.resize(factor_zoom).set_position("center")
    return CompositeVideoClip([imagen_zoom], size=(W, H)).set_duration(duracion)


# ============================================================
# 6. CONSTRUIR VIDEO FINAL DE UN TEMA
# ============================================================
def construir_video_tema(tema, guion, palabras_clave, ruta_salida):
    font = obtener_fuente(FONT_SIZE)

    # --- Audio y subtítulos, generados JUNTOS frase por frase (sync exacto) ---
    print("🎬 Generando audio y subtítulos sincronizados (frase por frase)...")
    audio_narracion, clip_subtitulos, duracion_narracion = construir_audio_y_subtitulos(guion, palabras_clave, font)
    duracion_subs = clip_subtitulos.duration
    print(f"   Duración real del audio: {duracion_narracion:.1f}s (subtítulos: {duracion_subs:.1f}s)")

    # --- CTA final: invita a seguir la cuenta, después de que termina el guion ---
    img_dummy = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_dummy = ImageDraw.Draw(img_dummy)
    cta_lineas = envolver_en_lineas(CTA_TEXTO.split(), font, draw_dummy, MAX_ANCHO_TEXTO)
    cta_img = renderizar_estado(cta_lineas, sum(len(l) for l in cta_lineas), CTA_PALABRAS_CLAVE, font)
    cta_clip = ImageClip(np.array(cta_img)).set_duration(CTA_DURACION).crossfadein(CTA_FADE_IN)
    clip_subtitulos = concatenate_videoclips([clip_subtitulos, cta_clip], method="compose")

    duracion_total = clip_subtitulos.duration
    print(f"   Duración total con CTA final: {duracion_total:.1f}s")

    # --- Fondo: imagen fija del tema con zoom lento (si existe), o el
    # video base loopeado como respaldo (comportamiento anterior) ---
    ruta_imagen_tema = f"{CARPETA_IMAGENES_TEMA}/tema{tema['id']}.jpg"
    if os.path.exists(ruta_imagen_tema):
        print(f"🖼️ Preparando fondo con imagen fija del tema (zoom lento): {ruta_imagen_tema}")
        video_loop = construir_clip_fondo_imagen(ruta_imagen_tema, duracion_total)
    else:
        print("🎥 No hay imagen para este tema, usando video base (respaldo)...")
        video_original = VideoFileClip(VIDEO_BASE_PATH).resize((W, H))
        n_loops = int(duracion_total // video_original.duration) + 1
        video_loop = concatenate_videoclips([video_original] * n_loops).subclip(0, duracion_total)

    if audio_narracion.duration < duracion_total:
        silencio = AudioClip(lambda t: [0, 0], duration=duracion_total - audio_narracion.duration)
        audio_narracion = concatenate_audioclips([audio_narracion, silencio])

    # --- Sonido ambiental de fondo (muy bajo, de fondo nada más) ---
    ruta_sonido = "output/ambiente.mp3"
    audio_ambiente = None
    if descargar_sonido_ambiental(tema["sonido_url"], ruta_sonido):
        try:
            amb = AudioFileClip(ruta_sonido)
            amb = audio_loop(amb, duration=duracion_total)
            audio_ambiente = volumex(amb, 0.12)
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
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
        }
        media = MediaFileUpload(ruta_video, chunksize=-1, resumable=True)
        req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        resp = req.execute()
        print("✅ Publicado en YouTube:", resp["id"], f"https://youtu.be/{resp['id']}")
    except Exception as e:
        print(f"❌ Error al publicar en YouTube: {e}")


# --- Instagram: helpers de almacenamiento temporal público del video ---
#
# La API de publicación de contenido de Instagram (a diferencia de la de
# Facebook) NO acepta subir el archivo de video directamente: exige una URL
# pública (video_url) de la que ella misma descarga el archivo. Como este
# pipeline no tiene ningún servidor propio ($0 de presupuesto), se usa un
# truco simple: subir el video como asset de un GitHub Release TEMPORAL del
# mismo repositorio (usando el GITHUB_TOKEN que Actions inyecta automáticamente
# en cada ejecución), lo que da una URL pública de descarga directa
# (browser_download_url). Ese release se borra apenas termina de publicarse,
# pase lo que pase (bloque finally), así no se acumulan releases viejos.
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
            "name": f"Video temporal (auto, para publicar en Instagram)",
            "body": "Release temporal creado automaticamente por generar_reel_v2.py solo para darle una URL publica al video antes de publicarlo en Instagram. Se borra automaticamente apenas termina.",
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
    print(f"✅ Video subido a release temporal de GitHub: {asset['browser_download_url']}")
    return release_id, tag, asset["browser_download_url"]


def borrar_release_temporal(release_id, tag):
    """Borra el release y su tag temporal. Se llama SIEMPRE (bloque finally),
    haya salido bien o mal la publicación en Instagram, para no dejar basura
    en el repositorio."""
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    try:
        requests.delete(f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/{release_id}", headers=headers, timeout=30)
        requests.delete(f"https://api.github.com/repos/{GITHUB_REPOSITORY}/git/refs/tags/{tag}", headers=headers, timeout=30)
        print("🧹 Release temporal borrado")
    except Exception as e:
        print(f"⚠️ No se pudo borrar el release temporal (no es grave, solo queda como basura en el repo): {e}")


def _publicar_contenedor_instagram(video_url, media_type, caption=None):
    """Crea un contenedor de media en Instagram (Reel o Historia), espera a
    que Instagram termine de descargar/procesar el video, y lo publica.
    media_type: "REELS" o "STORIES" (las Historias no admiten caption)."""
    url_contenedor = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
    data = {
        "media_type": media_type,
        "video_url": video_url,
        "access_token": FB_ACCESS_TOKEN,
    }
    if caption and media_type != "STORIES":
        data["caption"] = caption

    resp = requests.post(url_contenedor, data=data, timeout=60)
    resp.raise_for_status()
    contenedor_id = resp.json()["id"]

    # Instagram procesa el video de forma asíncrona (lo descarga de video_url,
    # lo transcodifica, etc.) — hay que esperar a que quede en estado FINISHED
    # antes de poder publicarlo. Reintenta cada 10s, hasta 5 minutos.
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
            raise Exception("El procesamiento del video en Instagram terminó en estado ERROR")

    if estado != "FINISHED":
        raise Exception(f"Timeout esperando que Instagram procese el video (último estado: {estado})")

    url_publicar = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
    resp2 = requests.post(url_publicar, data={"creation_id": contenedor_id, "access_token": FB_ACCESS_TOKEN}, timeout=60)
    resp2.raise_for_status()
    print(f"✅ Publicado en Instagram ({media_type}):", resp2.json())


def publicar_instagram_todo(ruta_video, titulo, descripcion):
    """Publica el video en Instagram como Reel Y como Historia. Sube el
    archivo UNA sola vez a un release temporal de GitHub (para no duplicar
    la subida) y lo borra al final, pase lo que pase."""
    if not IG_USER_ID:
        print("⚠️ IG_USER_ID no configurado, se omite publicación en Instagram.")
        return

    release_id = None
    tag = None
    try:
        nombre_archivo = os.path.basename(ruta_video)
        print("📤 Subiendo video a almacenamiento temporal (GitHub Release) para Instagram...")
        release_id, tag, video_url = subir_video_temporal_github(ruta_video, nombre_archivo)

        caption = f"{titulo}\n\n{descripcion}\n\n#motivacion #superacion #reflexion #psicologia"
        _publicar_contenedor_instagram(video_url, "REELS", caption=caption)
        _publicar_contenedor_instagram(video_url, "STORIES")

    except Exception as e:
        print(f"❌ Error al publicar en Instagram: {e}")
    finally:
        if release_id:
            borrar_release_temporal(release_id, tag)


# --- Facebook: Historia (Story) ---
# Endpoint dedicado /{page-id}/video_stories, en dos fases: "start" (crea el
# video_id y una upload_url) y "finish" (confirma y publica como Historia,
# una vez subido el binario). A diferencia de Instagram, Facebook sí acepta
# subir el archivo directo (no hace falta URL pública ni release temporal).
def publicar_historia_facebook(ruta_video):
    try:
        url_stories = f"https://graph.facebook.com/v19.0/{PAGE_ID}/video_stories"

        resp = requests.post(url_stories, data={"upload_phase": "start", "access_token": FB_ACCESS_TOKEN}, timeout=30)
        resp.raise_for_status()
        info = resp.json()
        video_id = info["video_id"]
        upload_url = info["upload_url"]

        with open(ruta_video, "rb") as f:
            video_bytes = f.read()

        headers_subida = {
            "Authorization": f"OAuth {FB_ACCESS_TOKEN}",
            "offset": "0",
            "file_size": str(len(video_bytes)),
        }
        r2 = requests.post(upload_url, headers=headers_subida, data=video_bytes, timeout=180)
        r2.raise_for_status()

        r3 = requests.post(url_stories, data={
            "upload_phase": "finish",
            "video_id": video_id,
            "access_token": FB_ACCESS_TOKEN,
        }, timeout=30)
        r3.raise_for_status()
        print("✅ Historia publicada en Facebook:", r3.json())
    except Exception as e:
        print(f"❌ Error al publicar Historia en Facebook: {e}")


# --- Threads: publicación de video ---
# API separada de Facebook/Instagram (graph.threads.net, no graph.facebook.com),
# pero el flujo es muy parecido: crear un contenedor de media con una URL
# pública de video, esperar a que termine de procesarse, y publicarlo.
# Threads no tiene Historias, solo publicaciones normales (como un post).
# Reutiliza el mismo mecanismo de release temporal de GitHub que Instagram
# para conseguir la URL pública del video.
def publicar_threads(ruta_video, titulo, descripcion):
    if not THREADS_ACCESS_TOKEN:
        print("⚠️ THREADS_ACCESS_TOKEN no configurado, se omite publicación en Threads.")
        return

    release_id = None
    tag = None
    try:
        nombre_archivo = os.path.basename(ruta_video)
        print("📤 Subiendo video a almacenamiento temporal (GitHub Release) para Threads...")
        release_id, tag, video_url = subir_video_temporal_github(ruta_video, nombre_archivo)

        texto = f"{titulo}\n\n{descripcion}"[:500]  # Threads limita el texto a 500 caracteres

        url_contenedor = "https://graph.threads.net/v1.0/me/threads"
        resp = requests.post(url_contenedor, data={
            "media_type": "VIDEO",
            "video_url": video_url,
            "text": texto,
            "access_token": THREADS_ACCESS_TOKEN,
        }, timeout=60)
        resp.raise_for_status()
        contenedor_id = resp.json()["id"]

        # Igual que Instagram: Threads procesa el video de forma asíncrona.
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
                raise Exception("El procesamiento del video en Threads terminó en estado ERROR")

        if estado != "FINISHED":
            raise Exception(f"Timeout esperando que Threads procese el video (último estado: {estado})")

        url_publicar = "https://graph.threads.net/v1.0/me/threads_publish"
        resp2 = requests.post(url_publicar, data={"creation_id": contenedor_id, "access_token": THREADS_ACCESS_TOKEN}, timeout=60)
        resp2.raise_for_status()
        print("✅ Publicado en Threads:", resp2.json())

    except Exception as e:
        print(f"❌ Error al publicar en Threads: {e}")
    finally:
        if release_id:
            borrar_release_temporal(release_id, tag)


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
            guion, palabras_clave = obtener_guion_del_dia(tema, model)
            ruta_salida = f"output/reel_tema{tema['id']}.mp4"
            construir_video_tema(tema, guion, palabras_clave, ruta_salida)

            if not args.no_publicar:
                titulo = tema["nombre"]
                descripcion = guion
                publicar_facebook(ruta_salida, titulo, descripcion)
                publicar_youtube(ruta_salida, titulo, descripcion)
                publicar_instagram_todo(ruta_salida, titulo, descripcion)
                publicar_historia_facebook(ruta_salida)
                publicar_threads(ruta_salida, titulo, descripcion)
            else:
                print("⏭️ --no-publicar activado, video generado pero no publicado.")

        except Exception as e:
            print(f"❌ Error procesando tema {tema['id']}: {e}")
            continue

    print("\n🎉 PROCESO COMPLETADO")


if __name__ == "__main__":
    main()
