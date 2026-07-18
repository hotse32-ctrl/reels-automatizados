# Automatización de Reels/Shorts con coste $0

Sistema que genera un guion diario sobre IA, crea imagen + audio + subtítulos, monta un video de 30s, y lo publica automáticamente en Facebook, Instagram, YouTube y TikTok usando GitHub Actions.

## Secretos necesarios (todos gratis)

| Secreto | Cómo obtenerlo | Coste |
|---|---|---|
| `GEMINI_API_KEY` | aistudio.google.com → Create API Key | $0 |
| `HF_TOKEN` | huggingface.co/settings/tokens → New token | $0 |
| `FACEBOOK_ACCESS_TOKEN` | developers.facebook.com → Crear app → Generar token de página | $0 |
| `FACEBOOK_PAGE_ID` | Tu página de Facebook → About → Page ID | $0 |
| `YOUTUBE_TOKEN_JSON` | console.cloud.google.com → YouTube Data API v3 → Credenciales OAuth 2.0 | $0 (10,000 unidades/día) |
| `TIKTOK_ACCESS_TOKEN` | developers.tiktok.com → Crear app empresarial → Obtener token | $0 (con aprobación) |
| `TELEGRAM_BOT_TOKEN` (opcional) | Token de @BotFather en Telegram | $0 |
| `TELEGRAM_CHAT_ID` (opcional) | Tu ID de chat vía @userinfobot | $0 |

Guárdalos en **Settings → Secrets and variables → Actions → New repository secret**.

## Configuración de YouTube OAuth 2.0

1. Crea un proyecto en console.cloud.google.com.
2. Habilita **YouTube Data API v3**.
3. Configura la pantalla de consentimiento → Externo → añade tu correo como usuario de prueba.
4. Credenciales → Crear ID de cliente OAuth → **Aplicación de escritorio**.
5. Descarga el JSON y guárdalo completo como texto en el secreto `YOUTUBE_TOKEN_JSON`.

## Primera ejecución

1. Ve a la pestaña **Actions** de este repositorio.
2. Ejecuta manualmente el workflow (botón "Run workflow").
3. Revisa los logs para verificar que todo funciona.

## Límites gratuitos (referencia)

| Recurso | Límite gratuito |
|---|---|
| GitHub Actions (repo público) | Ilimitado |
| Gemini API | 60 peticiones/min |
| Hugging Face API | Ilimitado (con cola) |
| gTTS | Ilimitado |
| Facebook Graph API | 200 llamadas/hora |
| YouTube Data API | 10,000 unidades/día (~1,600 por subida) |
| TikTok Business API | Varía |

**Coste total estimado: $0/mes.**
