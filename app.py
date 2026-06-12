import streamlit as st
import os
import json
import subprocess
from gtts import gTTS
from PIL import Image, ImageDraw
from openai import OpenAI

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

# 1. Intentar leer la clave directamente desde Streamlit Secrets de forma automática
if "OPENROUTER_API_KEY" in st.secrets and st.secrets["OPENROUTER_API_KEY"].strip() != "":
    api_key = st.secrets["OPENROUTER_API_KEY"]
    st.sidebar.success("🔒 API Key cargada automáticamente desde Secrets.")
else:
    # 2. Respaldo por si ejecutas el código en local o no has configurado los Secrets todavía
    api_key = st.sidebar.text_input(
        "OpenRouter API Key:", 
        type="password", 
        help="Introduce tu clave manualmente o configúrala en el apartado Secrets de Streamlit Cloud."
    )

# Inputs principales en la pantalla central
tema = st.text_input("Tema del documental:", "El origen templario de un castillo medieval")
duracion = st.selectbox("Duración del video:", ["1 Minuto (Modo MVP)", "30 Minutos (Escala en Servidor)", "50 Minutos (Escala en Servidor)"])

# Asegurar que existan las carpetas temporales necesarias para procesar el contenido
for carpeta in ["temp_audio", "temp_images", "temp_scenes"]:
    os.makedirs(carpeta, exist_ok=True)

# =====================================================================
# FUNCIONES AUXILIARES DEL PIPELINE (PROCESAMIENTO MULTIMEDIA)
# =====================================================================

def obtener_duracion_audio(archivo_audio):
    """Utiliza ffprobe para medir la duración exacta del audio generado en segundos."""
    comando = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {archivo_audio}"
    duracion = subprocess.check_output(comando, shell=True)
    return float(duracion.strip())

def crear_imagen(texto, color, ruta):
    """Genera una imagen fija (placeholder) con Pillow usando el fondo sugerido por la IA."""
    img = Image.new('RGB', (1920, 1080), color=color)
    d = ImageDraw.Draw(img)
    # Escribe el prompt visual simulado en el centro de la imagen para el MVP
    d.text((100, 500), texto, fill="#ffffff")
    img.save(ruta)

def crear_clip(ruta_img, ruta_aud, duracion, ruta_out):
    """
    Versión corregida y ultra compatible para el MVP.
    Fuerza una tasa de fotogramas constante (25fps) y mapea correctamente los canales
    para que la unión posterior sin re-codificación (-c copy) no rompa el canal de video.
    """
    comando = (
        f"ffmpeg -y -loop 1 -framerate 25 -i {ruta_img} -i {ruta_aud} "
        f"-c:v libx264 -tune stillimage -c:a aac -b:a 192k -pix_fmt yuv420p "
        f"-map 0:v:0 -map 1:a:0 -shortest {ruta_out}"
    )
    subprocess.run(comando, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# =====================================================================
# EJECUCIÓN DEL PIPELINE (BOTÓN PRINCIPAL)
# =====================================================================
if st.button("🚀 Lanzar Pipeline"):
    if not api_key:
        st.error("Por favor, introduce tu API Key de OpenRouter en la barra lateral izquierda o en el apartado de Secrets.")
    else:
        barra_progreso = st.progress(0)
        texto_estado = st.empty()
        
        # -----------------------------------------------------------------
        # FASE 1: Llamada a Qwen3.7-Max para generar Estructura y Guión
        # -----------------------------------------------------------------
        texto_estado.text("Qwen3.7-Max está analizando el tema y redactando el guión...")
        
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        
        prompt_sistema = (
            "Actúas como un guionista profesional de documentales históricos. Tu tarea es estructurar un "
            "video corto de 1 minuto sobre el tema que te dará el usuario. Debes dividir el video en exactamente 5 bloques o escenas. "
            "Debes responder EXCLUSIVAMENTE con un array JSON válido, sin textos introductorios ni bloques de código markdown. "
            "Cada objeto del array debe contener exactamente las siguientes llaves:\n"
            "- id: entero consecutivo (1 al 5)\n"
            "- texto: la narración en español que leerá el locutor (aproximadamente 10-12 segundos de lectura)\n"
            "- color: un código hexadecimal oscuro representativo de la atmósfera visual de la escena (ej. #1a2a3a)\n"
            "- visual: un prompt detallado en inglés para una IA generadora de imágenes hiperrealistas (estilo cinematográfico)."
        )
        
        try:
            response = client.chat.completions.create(
                model="qwen/qwen3.7-max",
                messages=[
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": f"Tema del documental: {tema}"}
                ],
                temperature=0.7
            )
            
            # Sanitizar la respuesta en caso de que Qwen devuelva bloques markdown (```json ... ```)
            raw_content = response.choices[0].message.content.strip()
            if raw_content.startswith("```json"):
                raw_content = raw_content.replace("```json", "").replace("```", "").strip()
            elif raw_content.startswith("```"):
                raw_content = raw_content.replace("```", "").strip()
            
            ESCENAS_JSON = json.loads(raw_content)
            texto_estado.text("¡Guión estructurado correctamente por Qwen!")
            barra_progreso.progress(20)
            
            # -----------------------------------------------------------------
            # FASE 2: Generación y procesamiento de elementos multimedia
            # -----------------------------------------------------------------
            lista_clips = []
            total_escenas = len(ESCENAS_JSON)
            
            for i, escena in enumerate(ESCENAS_JSON):
                id_e = escena["id"]
                texto_estado.text(f"Procesando escena {id_e} de {total_escenas}...")
                
                # A. Renderizar Audio (Utiliza gTTS de forma local y gratuita)
                r_audio = f"temp_audio/audio_{id_e}.mp3"
                tts = gTTS(text=escena["texto"], lang='es', tld='es')
                tts.save(r_audio)
                dur = obtener_duracion_audio(r_audio)
                
                # B. Renderizar Imagen (Pillow genera el fondo de color con el texto del prompt de Qwen)
                r_imagen = f"temp_images/imagen_{id_e}.png"
                texto_pantalla = f"Prompt IA Visual ideado por Qwen:\n{escena['visual'][:80]}..."
                crear_imagen(texto_pantalla, escena["color"], r_imagen)
                
                # C. Convertir a micro-video clip parcial (.mp4 de duración exacta al audio)
                r_clip = f"temp_scenes/escena_{id_e}.mp4"
                crear_clip(r_imagen, r_audio, dur, r_clip)
                
                lista_clips.append(r_clip)
                # El progreso escala del 20% al 80% durante esta generación por bloques
                barra_progreso.progress(int(20 + ((i + 1) / total_escenas) * 60))
                
            # -----------------------------------------------------------------
            # FASE 3: Concatenación final del video maestro
            # -----------------------------------------------------------------
            texto_estado.text("Ensamblando todas las escenas con FFmpeg...")
            
            # Crear el archivo de texto que requiere el filtro concat de FFmpeg
            with open("lista_videos.txt", "w") as f:
                for clip in lista_clips:
                    f.write(f"file '{clip}'\n")
                    
            video_final = "resultado_qwen_mvp.mp4"
            # Une los videos de forma nativa e instantánea compartiendo propiedades constantes de códec
            comando_final = f"ffmpeg -y -f concat -safe 0 -i lista_videos.txt -c copy {video_final}"
            subprocess.run(comando_final, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Limpieza del archivo de texto auxiliar
            if os.path.exists("lista_videos.txt"):
                os.remove("lista_videos.txt")
                
            barra_progreso.progress(100)
            texto_estado.text("¡Video documental renderizado con éxito!")
            
            # -----------------------------------------------------------------
            # FASE 4: Visualización y descarga del entregable
            # -----------------------------------------------------------------
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
