import streamlit as st
import os
import json
import time
import requests
import urllib.parse
import io
import subprocess
from gtts import gTTS
from PIL import Image, ImageDraw

# =====================================================================
# CONFIGURACIÓN DE LA INTERFAZ DE STREAMLIT
# =====================================================================
st.set_page_config(page_title="Qwen3.7 Documental Studio", page_icon="🎬", layout="centered")

st.title("🎬 Productor de Documentales con Qwen3.7-Max")
st.write("Escribe un tema y deja que la IA de Alibaba diseñe el guión y los prompts visuales en tiempo real.")

# =====================================================================
# CONFIGURACIÓN DE CREDENCIALES (SECRETS / BARRA LATERAL)
# =====================================================================
st.sidebar.header("Configuración de IA")

if "OPENROUTER_API_KEY" in st.secrets and st.secrets["OPENROUTER_API_KEY"].strip() != "":
    api_key = st.secrets["OPENROUTER_API_KEY"]
    st.sidebar.success("🔒 API Key cargada automáticamente desde Secrets.")
else:
    api_key = st.sidebar.text_input(
        "OpenRouter API Key:", 
        type="password", 
        help="Introduce tu clave manualmente o configúrala en el apartado Secrets de Streamlit Cloud."
    )

# Inputs principales en la pantalla central
tema = st.text_input("Tema del documental:", "Pokemon Gengar que habilidades tiene")
duracion = st.selectbox("Duración del video:", ["1 Minuto (Modo MVP)", "30 Minutos (Escala en Servidor)", "50 Minutos (Escala en Servidor)"])

# Asegurar carpetas temporales
for carpeta in ["temp_audio", "temp_images", "temp_scenes"]:
    os.makedirs(carpeta, exist_ok=True)

# =====================================================================
# FUNCIONES AUXILIARES DEL PIPELINE (PROCESAMIENTO MULTIMEDIA)
# =====================================================================

def obtener_duracion_audio(archivo_audio):
    comando = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {archivo_audio}"
    duracion = subprocess.check_output(comando, shell=True)
    return float(duracion.strip())

def limpiar_acentos(texto):
    """Reemplaza caracteres acentuados para evitar cajas vacías o rotas en Pillow sin fuentes externas."""
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', 'ü': 'u', 'Ü': 'U'
    }
    for original, nuevo in replacements.items():
        texto = texto.replace(original, nuevo)
    return texto

def crear_imagen(prompt_texto, texto_narracion, color_hex, id_escena, tema_general):
    """
    Descarga una imagen cinematográfica real burlando los bloqueos de Cloudflare
    mediante cabeceras de navegación simuladas completas.
    """
    img = None
    
    # Cabeceras completas de simulación de navegador de escritorio para evitar bloqueos anti-bot (Cloudflare/AWS)
    headers_humanos = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }
    
    # Sanitizar concepto de búsqueda primario (ej: "pokemon gengar")
    busqueda_concepto = tema_general.lower().replace("que habilidades tiene", "").replace("documental", "").strip()
    query_api = urllib.parse.quote(busqueda_concepto)
    
    # INTENTO 1: Buscar imágenes de calidad pre-renderizadas en el índice de Lexica Art
    try:
        url_lexica = f"https://lexica.art/api/v1/search?q={query_api}"
        response = requests.get(url_lexica, headers=headers_humanos, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get("images") and len(data["images"]) > id_escena:
                img_url = data["images"][id_escena]["src"]
                # Descargar el archivo binario de la imagen usando las mismas cabeceras humanas
                img_res = requests.get(img_url, headers=headers_humanos, timeout=15)
                if img_res.status_code == 200:
                    img = Image.open(io.BytesIO(img_res.content)).convert('RGB')
    except Exception:
        pass

    # INTENTO 2 (FALLBACK): Si el índice es bloqueado, forzar renderizado directo con Pollinations con prompt limpio
    if img is None:
        try:
            prompt_directo = urllib.parse.quote(f"cinematic dark dramatic photo of {busqueda_concepto}")
            url_pollinations = f"https://image.pollinations.ai/p/{prompt_directo}?width=1920&height=1080&nologo=true&seed={id_escena * 10}"
            img_res = requests.get(url_pollinations, headers=headers_humanos, timeout=20)
            if img_res.status_code == 200:
                img = Image.open(io.BytesIO(img_res.content)).convert('RGB')
        except Exception:
            pass

    # INTENTO 3 (FALLBACK DE SEGURIDAD): Lienzo de color plano si todo el tráfico externo es bloqueado
    if img is None:
        img = Image.new('RGB', (1920, 1080), color=color_hex)
        d_fail = ImageDraw.Draw(img)
        d_fail.rectangle([(40, 40), (1880, 1040)], outline="#ffffff", width=4)
    else:
        # Reescalar y recortar inteligentemente la imagen obtenida a proporción horizontal exacta 16:9 (1920x1080)
        target_width = 1920
        target_height = 1080
        img_aspect = img.width / img.height
        target_aspect = target_width / target_height

        if img_aspect > target_aspect:
            new_height = target_height
            new_width = int(new_height * img_aspect)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            left = (new_width - target_width) // 2
            img = img.crop((left, 0, left + target_width, target_height))
        else:
            new_width = target_width
            new_height = int(new_width / img_aspect)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            top = (new_height - target_height) // 2
            img = img.crop((0, top, target_width, top + target_height))

    # Construir y quemar los bloques de subtítulos translúcidos inferiores
    texto_limpio = limpiar_acentos(texto_narracion)
    palabras = texto_limpio.split()
    lineas = []
    linea_actual = ""
    for palabra in palabras:
        if len(linea_actual + " " + palabra) < 65:
            linea_actual += " " + palabra
        else:
            lineas.append(linea_actual.strip())
            linea_actual = palabra
    lineas.append(linea_actual.strip())
    
    num_lineas = min(len(lineas), 3)
    altura_barra = 80 + (num_lineas * 50)
    
    capa_transparente = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw_layer = ImageDraw.Draw(capa_transparente)
    draw_layer.rectangle([(0, 1080 - altura_barra), (1920, 1080)], fill=(0, 0, 0, 165))
    
    img = Image.alpha_composite(img.convert('RGBA'), capa_transparente).convert('RGB')
    d = ImageDraw.Draw(img)
    
    try:
        from PIL import ImageFont
        fuente_subtitulo = ImageFont.load_default(size=42)
    except Exception:
        fuente_subtitulo = ImageFont.load_default()
        
    y_offset = 1080 - altura_barra + 35
    for linea in lineas[:3]:
        ancho_estimado = len(linea) * 19
        x_pos = max(100, (1920 - ancho_estimado) // 2)
        d.text((x_pos, y_offset), linea, fill="#ffffff", font=fuente_subtitulo)
        y_offset += 50

    img.save(f"temp_images/imagen_{id_escena}.png")

def crear_clip(ruta_img, ruta_aud, duracion, ruta_out):
    comando = (
        f"ffmpeg -y -loop 1 -framerate 25 -i {ruta_img} -i {ruta_aud} "
        f"-c:v libx264 -tune stillimage -c:a aac -b:a 192k -pix_fmt yuv420p "
        f"-map 0:v:0 -map 1:a:0 -shortest {ruta_out}"
    )
    subprocess.run(comando, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# =====================================================================
# MOTOR DE CONEXIÓN CON REINTENTOS PARA QWEN3.7-MAX
# =====================================================================
def consultar_qwen_con_retries(tema_solicitado, key):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://streamlit.io",
        "X-Title": "Qwen Documental Studio"
    }
    
    prompt_sistema = (
        "Actúas como un guionista profesional de documentales. Tu tarea es estructurar un "
        "video corto de 1 minuto sobre el tema que te dará el usuario. Debes dividir el video en exactamente 5 bloques o escenas. "
        "Debes responder EXCLUSIVAMENTE con un array JSON válido, sin textos introductorios ni bloques de código markdown. "
        "Cada objeto del array debe contener exactamente las siguientes llaves:\n"
        "- id: entero consecutivo (1 al 5)\n"
        "- texto: la narración en español que leerá el locutor (aproximadamente 10-12 segundos de lectura)\n"
        "- color: un código hexadecimal oscuro representativo de la atmósfera de la escena (ej. #1a2a3a)\n"
        "- visual: un prompt detallado en inglés para una IA generadora de imágenes hiperrealistas (estilo cinematográfico)."
    )
    
    payload = {
        "model": "qwen/qwen3.7-max",
        "messages": [
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": f"Tema del documental: {tema_solicitado}"}
        ],
        "temperature": 0.7
    }
    
    reintentos = 5
    delay_inicial = 1
    
    for intento in range(reintentos):
        try:
            status_placeholder.text(f"Conectando con Qwen3.7-Max (Intento {intento + 1}/{reintentos})...")
            response = requests.post(url, headers=headers, json=payload, timeout=45)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                status_placeholder.warning(f"Límite de peticiones alcanzado. Esperando para reintentar...")
                time.sleep(delay_inicial * 2)
            else:
                raise Exception(f"Servidor respondió con código {response.status_code}: {response.text}")
                
        except Exception as e:
            if intento == reintentos - 1:
                raise Exception(f"No se pudo establecer conexión tras {reintentos} intentos. Detalle: {e}")
            time.sleep(delay_inicial)
            delay_inicial *= 2

# =====================================================================
# EJECUCIÓN DEL PIPELINE (BOTÓN PRINCIPAL)
# =====================================================================
if st.button("🚀 Lanzar Pipeline"):
    if not api_key:
        st.error("Por favor, introduce tu API Key de OpenRouter.")
    else:
        barra_progreso = st.progress(0)
        status_placeholder = st.empty()
        
        try:
            response_data = consultar_qwen_con_retries(tema, api_key)
            raw_content = response_data["choices"][0]["message"]["content"].strip()
            
            ticks = chr(96) * 3
            if raw_content.startswith(f"{ticks}json"):
                raw_content = raw_content.replace(f"{ticks}json", "").replace(ticks, "").strip()
            elif raw_content.startswith(ticks):
                raw_content = raw_content.replace(ticks, "").strip()
            
            ESCENAS_JSON = json.loads(raw_content)
            status_placeholder.success("¡Guión estructurado correctamente por Qwen!")
            barra_progreso.progress(20)
            
            lista_clips = []
            total_escenas = len(ESCENAS_JSON)
            
            for i, escena in enumerate(ESCENAS_JSON):
                id_e = escena["id"]
                status_placeholder.text(f"Generando escena {id_e} de {total_escenas}...")
                
                # A. Audio
                r_audio = f"temp_audio/audio_{id_e}.mp3"
                tts = gTTS(text=escena["texto"], lang='es', tld='es')
                tts.save(r_audio)
                dur = obtener_duracion_audio(r_audio)
                
                # B. Imagen
                r_imagen = f"temp_images/imagen_{id_e}.png"
                crear_imagen(escena["visual"], escena["texto"], escena["color"], id_e, tema)
                
                # C. Video clip parcial
                r_clip = f"temp_scenes/escena_{id_e}.mp4"
                crear_clip(r_imagen, r_audio, dur, r_clip)
                
                lista_clips.append(r_clip)
                barra_progreso.progress(int(20 + ((i + 1) / total_escenas) * 60))
                
            # Concatenación final de las escenas
            status_placeholder.text("Ensamblando todas las escenas con FFmpeg...")
            with open("lista_videos.txt", "w") as f:
                for clip in lista_clips:
                    f.write(f"file '{clip}'\n")
                    
            video_final = "resultado_qwen_mvp.mp4"
            comando_final = f"ffmpeg -y -f concat -safe 0 -i lista_videos.txt -c copy {video_final}"
            subprocess.run(comando_final, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if os.path.exists("lista_videos.txt"):
                os.remove("lista_videos.txt")
                
            barra_progreso.progress(100)
            status_placeholder.text("¡Video documental renderizado con éxito!")
            
            if os.path.exists(video_final):
                with open(video_final, "rb") as file:
                    st.video(file.read())
                    
                st.download_button(
                    label="📥 Descargar Video Documental (.mp4)",
                    data=open(video_final, "rb"),
                    file_name="documental_qwen_ia.mp4",
                    mime="video/mp4"
                )
                
        except Exception as e:
            st.error(f"Error crítico en el flujo del sistema: {e}")
