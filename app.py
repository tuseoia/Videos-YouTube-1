import streamlit as st
import os
import json
import subprocess
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont
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

def crear_imagen(prompt_texto, texto_narracion, color_hex, id_escena):
    """Genera una tarjeta visual de alta definición, legible y limpia para el MVP."""
    # Crear lienzo Full HD
    img = Image.new('RGB', (1920, 1080), color=color_hex)
    d = ImageDraw.Draw(img)
    
    # Cargar fuente por defecto escalada (Pillow 10.1.0+ nativo)
    try:
        fuente_titulo = ImageFont.load_default(size=60)
        fuente_cuerpo = ImageFont.load_default(size=40)
    except Exception:
        fuente_titulo = ImageFont.load_default()
        fuente_cuerpo = ImageFont.load_default()
    
    # Dibujar un marco elegante en los bordes para demostrar que hay video activo
    d.rectangle([(40, 40), (1880, 1040)], outline="#ffffff", width=4)
    
    # Cabecera de la escena
    d.text((100, 100), f"ESCENA GENERAL AUTOMÁTICA {id_escena} / 5", fill="#ffcc00", font=fuente_titulo)
    
    # Sección 1: Lo que ideó la IA para el prompt de imagen
    d.text((100, 250), "PROMPT VISUAL ENVIADO A LA IA:", fill="#aaaaaa", font=fuente_cuerpo)
    
    # Ajustar líneas del prompt para que no se salgan de la pantalla
    palabras_prompt = prompt_texto.split()
    lineas_prompt = []
    linea_actual = ""
    for palabra in palabras_prompt:
        if len(linea_actual + " " + palabra) < 65:
            linea_actual += " " + palabra
        else:
            lineas_prompt.append(linea_actual.strip())
            linea_actual = palabra
    lineas_prompt.append(linea_actual.strip())
    
    y_offset = 320
    for linea in lineas_prompt[:4]: # Límite de 4 líneas para el prompt
        d.text((100, y_offset), linea, fill="#ffffff", font=fuente_cuerpo)
        y_offset += 55
        
    # Sección 2: Lo que está diciendo el locutor en este instante
    d.text((100, 650), "AUDIO NARRACIÓN ACTUAL (SUBTÍTULO):", fill="#ffcc00", font=fuente_cuerpo)
    
    palabras_nar = texto_narracion.split()
    lineas_nar = []
    linea_actual = ""
    for palabra in palabras_nar:
        if len(linea_actual + " " + palabra) < 65:
            linea_actual += " " + palabra
        else:
            lineas_nar.append(linea_actual.strip())
            linea_actual = palabra
    lineas_nar.append(linea_actual.strip())
    
    y_offset = 720
    for linea in lineas_nar[:4]:
        d.text((100, y_offset), linea, fill="#ffffff", font=fuente_cuerpo)
        y_offset += 55

    img.save(ruta_imagen)

def crear_clip(ruta_img, ruta_aud, duracion, ruta_out):
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
        st.error("Por favor, introduce tu API Key de OpenRouter.")
    else:
        barra_progreso = st.progress(0)
        texto_estado = st.empty()
        
        texto_estado.text("Qwen3.7-Max está analizando el tema y redactando el guión...")
        
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        
        prompt_sistema = (
            "Actúas como un guionista profesional de documentales. Tu tarea es estructurar un "
            "video corto de 1 minuto sobre el tema que te dará el usuario. Debes dividir el video en exactamente 5 bloques. "
            "Debes responder EXCLUSIVAMENTE con un array JSON válido, sin textos introductorios ni bloques markdown. "
            "Cada objeto del array debe contener exactamente las siguientes llaves:\n"
            "- id: entero consecutivo (1 al 5)\n"
            "- texto: la narración en español que leerá el locutor (unos 10-12 segundos de lectura)\n"
            "- color: un código hexadecimal oscuro representativo de la atmósfera de la escena (ej. #1a2a3a)\n"
            "- visual: un prompt detallado en inglés para una IA generadora de imágenes hiperrealistas."
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
            
            raw_content = response.choices[0].message.content.strip()
            if raw_content.startswith("```json"):
                raw_content = raw_content.replace("
```json", "").replace("```", "").strip()
            elif raw_content.startswith("```"):
                raw_content = raw_content.replace("
```", "").strip()
            
            ESCENAS_JSON = json.loads(raw_content)
            texto_estado.text("¡Guión estructurado correctamente por Qwen!")
            barra_progreso.progress(20)
            
            lista_clips = []
            total_escenas = len(ESCENAS_JSON)
            
            for i, escena in enumerate(ESCENAS_JSON):
                id_e = escena["id"]
                texto_estado.text(f"Procesando escena {id_e} de {total_escenas}...")
                
                # A. Audio
                r_audio = f"temp_audio/audio_{id_e}.mp3"
                tts = gTTS(text=escena["texto"], lang='es', tld='es')
                tts.save(r_audio)
                dur = obtener_duracion_audio(r_audio)
                
                # B. Imagen (Con la nueva función de diseño escalado y textos de la IA)
                r_imagen = f"temp_images/imagen_{id_e}.png"
                crear_imagen(escena["visual"], escena["texto"], escena["color"], id_e)
                
                # C. Video clip parcial (.mp4)
                r_clip = f"temp_scenes/escena_{id_e}.mp4"
                crear_clip(r_imagen, r_audio, dur, r_clip)
                
                lista_clips.append(r_clip)
                barra_progreso.progress(int(20 + ((i + 1) / total_escenas) * 60))
                
            # Concatenación final
            texto_estado.text("Ensamblando todas las escenas con FFmpeg...")
            with open("lista_videos.txt", "w") as f:
                for clip in lista_clips:
                    f.write(f"file '{clip}'\n")
                    
            video_final = "resultado_qwen_mvp.mp4"
            comando_final = f"ffmpeg -y -f concat -safe 0 -i lista_videos.txt -c copy {video_final}"
            subprocess.run(comando_final, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if os.path.exists("lista_videos.txt"):
                os.remove("lista_videos.txt")
                
            barra_progreso.progress(100)
            texto_estado.text("¡Video documental renderizado con éxito!")
            
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
