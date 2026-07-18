import os
import requests
import json
import time
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import *
from moviepy.audio.fx.all import audio_loop
from gtts import gTTS
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ============================================================
# 1. CONFIGURACION DE VARIABLES DE ENTORNO
# ============================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
HF_TOKEN = os.environ.get("HF_TOKEN")
FB_ACCESS_TOKEN = os.environ.get("FACEBOOK_ACCESS_TOKEN")
PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID")
YOUTUBE_TOKEN_JSON = os.environ.get("YOUTUBE_TOKEN_JSON")
TIKTOK_ACCESS_TOKEN = os.environ.get("TIKTOK_ACCESS_TOKEN")

# Crear carpeta de salida
os.makedirs("output", exist_ok=True)

# ============================================================
# 2. GENERAR GUION CON GEMINI API (GRATIS)
# ============================================================
print("Generando guion...")

try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-flash-latest')
    prompt_guion = """
Genera un guion para un Reel de 30 segundos sobre inteligencia artificial.
Formato obligatorio:
- Gancho (primeros 3 segundos): frase impactante que enganche
- Desarrollo (20 segundos): 3 datos curiosos o utiles sobre IA
- CTA (ultimos 7 segundos): invita a dar like, comentar y compartir

Devuelve SOLO el texto del guion, sin introducciones ni explicaciones adicionales.
"""

    respuesta = model.generate_content(prompt_guion)
    guion = respuesta.text
    print("Guion generado correctamente")

except Exception as e:
    print(f"Error al generar guion: {e}")
    # Guion de respaldo
    guion = """
Sabias que la IA puede crear arte?
Dato 1: La IA generativa crea imagenes desde texto.
Dato 2: Los modelos de lenguaje entienden 100+ idiomas.
Dato 3: La IA ayuda a diagnosticar enfermedades.
Dale like y comenta que tema quieres para manana.
"""
    print("Usando guion de respaldo")

# ============================================================
# 3. GENERAR IMAGEN CON HUGGING FACE API (GRATIS)
# ============================================================
print("Generando imagen...")

try:
    HF_API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2-1"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}

    payload = {
        "inputs": f"Imagen principal para un video sobre inteligencia artificial: {guion[:200]}, formato 9:16, colores vibrantes, estilo moderno y futurista, alta calidad",
        "parameters": {
            "negative_prompt": "feo, borroso, distorsionado, baja calidad, texto, palabras",
            "num_inference_steps": 30
        }
    }

    response = requests.post(HF_API_URL, headers=headers, json=payload, timeout=60)

    if response.status_code == 200:
        with open("output/imagen_base.png", "wb") as f:
            f.write(response.content)
        print("Imagen generada correctamente")
    else:
        raise Exception(f"Error {response.status_code}: {response.text}")

except Exception as e:
    print(f"Error al generar imagen: {e}")
    # Imagen de respaldo (fondo degradado con texto)
    img = Image.new('RGB', (1080, 1920), color=(20, 30, 80))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 60)
    except:
        font = ImageFont.load_default()
    draw.text((540, 960), "INTELIGENCIA\nARTIFICIAL", fill="white", anchor="mm", font=font, align="center")
    img.save("output/imagen_base.png")
    print("Usando imagen de respaldo")

# ============================================================
# 4. GENERAR AUDIO CON GTTS (GRATIS, TEXTO A VOZ)
# ============================================================
print("Generando audio...")

try:
    # Limitar el texto a 500 caracteres (limite de gTTS)
    texto_audio = guion[:500]
    tts = gTTS(text=texto_audio, lang="es", slow=False)
    tts.save("output/audio_guion.mp3")
    print("Audio generado correctamente")

except Exception as e:
    print(f"Error al generar audio: {e}")
    # Audio de respaldo (silencio de 30 segundos)
    from moviepy.audio.io.AudioFileClip import AudioFileClip
    # Crear un audio mudo
    from moviepy.audio.AudioClip import AudioClip
    def make_frame(t):
        return [0, 0]  # Silencio
    audio_respaldo = AudioClip(make_frame, duration=30)
    audio_respaldo.write_audiofile("output/audio_guion.mp3", fps=44100)
    print("Usando audio de respaldo (silencio)")

# ============================================================
# 5. MONTAR VIDEO CON MOVIEPY (GRATIS)
# ============================================================
print("Montando video...")

try:
    # Cargar y redimensionar imagen
    imagen = Image.open("output/imagen_base.png")
    imagen = imagen.resize((1080, 1920))
    imagen.save("output/imagen_base_resized.png")

    # Crear clip de imagen (30 segundos)
    clip_imagen = ImageClip("output/imagen_base_resized.png").set_duration(30)

    # Cargar audio
    audio_clip = AudioFileClip("output/audio_guion.mp3")

    # Ajustar duracion del audio si es mas corto
    if audio_clip.duration < 30:
        audio_clip = audio_loop(audio_clip, duration=30)
    elif audio_clip.duration > 30:
        audio_clip = audio_clip.subclip(0, 30)

    # Crear subtitulos (texto en la parte inferior)
    txt_clip = TextClip(
        guion[:350],
        fontsize=45,
        color='white',
        stroke_color='black',
        stroke_width=3,
        font='DejaVu-Sans-Bold',
        method='caption',
        size=(900, None)
    ).set_position(('center', 0.80), relative=True).set_duration(30)

    # Combinar todo
    video_final = CompositeVideoClip([clip_imagen, txt_clip])
    video_final = video_final.set_audio(audio_clip)

    # Exportar video
    video_final.write_videofile(
        "output/reel_final.mp4",
        fps=24,
        codec='libx264',
        audio_codec='aac',
        threads=4,
        verbose=False,
        logger=None
    )
    print("Video montado correctamente: output/reel_final.mp4")

except Exception as e:
    print(f"Error al montar video: {e}")
    # Salir si falla el montaje
    exit(1)

# ============================================================
# 6. PUBLICAR EN FACEBOOK E INSTAGRAM (GRAPH API, GRATIS)
# ============================================================
print("Publicando en Facebook e Instagram...")

try:
    url_fb = f"https://graph.facebook.com/v19.0/{PAGE_ID}/videos"
    files = {'source': open('output/reel_final.mp4', 'rb')}
    data = {
        'access_token': FB_ACCESS_TOKEN,
        'title': 'Curiosidad de IA del dia',
        'description': guion[:200],
        'published': 'true'
    }

    resp_fb = requests.post(url_fb, files=files, data=data, timeout=120)

    if resp_fb.status_code == 200:
        print("Publicado en Facebook/Instagram:", resp_fb.json())
    else:
        print(f"Error en Facebook: {resp_fb.status_code} - {resp_fb.text}")

except Exception as e:
    print(f"Excepcion al publicar en Facebook: {e}")

# ============================================================
# 7. PUBLICAR EN YOUTUBE (YOUTUBE DATA API V3, GRATIS)
# ============================================================
print("Publicando en YouTube...")

try:
    # Cargar credenciales OAuth desde el JSON
    # Nota: El archivo JSON debe estar guardado como secreto en GitHub
    # y convertido a string, o subido directamente al repositorio
    with open("youtube_token.json", "w") as f:
        f.write(YOUTUBE_TOKEN_JSON)

    creds = Credentials.from_authorized_user_file("youtube_token.json")
    youtube = build('youtube', 'v3', credentials=creds)

    body = {
        'snippet': {
            'title': 'Curiosidad de IA - Reel Diario',
            'description': f"{guion[:500]}\n\n#IA #InteligenciaArtificial #Curiosidades #Shorts",
            'tags': ['IA', 'inteligencia artificial', 'curiosidades', 'shorts', 'tecnologia'],
            'categoryId': '22'  # Categoria: Ciencia y Tecnologia
        },
        'status': {
            'privacyStatus': 'unlisted',  # 'public', 'private', 'unlisted'
            'selfDeclaredMadeForKids': False
        }
    }

    media = MediaFileUpload('output/reel_final.mp4', chunksize=-1, resumable=True)
    request_youtube = youtube.videos().insert(
        part='snippet,status',
        body=body,
        media_body=media
    )
    response_yt = request_youtube.execute()
    print("Publicado en YouTube:", response_yt['id'])
    print(f"URL: https://youtu.be/{response_yt['id']}")

except Exception as e:
    print(f"Error al publicar en YouTube: {e}")
    print("El video esta disponible como artefacto descargable")

# ============================================================
# 8. PUBLICAR EN TIKTOK (TIKTOK BUSINESS API, GRATIS CON APROBACION)
# ============================================================
print("Publicando en TikTok...")

if TIKTOK_ACCESS_TOKEN:
    try:
        url_tk = "https://open-api.tiktok.com/share/video/upload/"
        files_tk = {'video': open('output/reel_final.mp4', 'rb')}
        data_tk = {
            'access_token': TIKTOK_ACCESS_TOKEN,
            'title': guion[:200],
            'privacy_level': 'public'
        }

        resp_tk = requests.post(url_tk, files=files_tk, data=data_tk, timeout=120)

        if resp_tk.status_code == 200:
            print("Publicado en TikTok:", resp_tk.json())
        else:
            print(f"Error en TikTok: {resp_tk.status_code} - {resp_tk.text}")

    except Exception as e:
        print(f"Excepcion al publicar en TikTok: {e}")
else:
    print("TikTok no configurado (falta TIKTOK_ACCESS_TOKEN), saltando...")

# ============================================================
# 9. FINALIZAR
# ============================================================
print("PROCESO COMPLETADO CON EXITO")
print("Video guardado en: output/reel_final.mp4")

# ============================================================
# 10. NOTIFICACION POR TELEGRAM (OPCIONAL)
# ============================================================
try:
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        mensaje = "Nuevo Reel publicado:\n"
        mensaje += f"YouTube: https://youtu.be/{response_yt['id']}\n" if 'response_yt' in locals() else ""
        mensaje += "Facebook/Instagram: publicado\n"
        mensaje += f"Guion: {guion[:200]}..."

        url_telegram = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data_telegram = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': mensaje,
            'parse_mode': 'HTML'
        }
        requests.post(url_telegram, data=data_telegram, timeout=10)
        print("Notificacion enviada a Telegram")

except Exception as e:
    print(f"Error al enviar notificacion Telegram: {e}")
