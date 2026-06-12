import streamlit as st
import os
import json
import subprocess
from gtts import gTTS
from PIL import Image, ImageDraw
from openai import OpenAI

# Configuración de la página de Streamlit
st.set_page_config(page_title="Qwen3.7 Documental Studio", page_icon="🎬", layout="centered")

st.title("🎬 Productor de Documentales con Qwen3.7-Max")
st.write("Escribe un tema y deja que la IA de Alibaba diseñe el guión y los prompts visuales.")

# Configuración de la API Key en la barra lateral
st.sidebar.header("Configuración de IA")
api_key = st.sidebar.text_input("OpenRouter API Key:", type="password", help="Consigue tu clave en openrouter.ai")

# Inputs principales
tema = st.text_input("Tema del documental:", "El origen templario de un castillo medieval")
duracion = st.selectbox("Duración del video:", ["1 Minuto (Modo MVP)", "30 Minutos (Escala en Servidor)", "50 Minutos (Escala en Servidor)"])

# Asegurar carpetas temporales
for carpeta in ["temp_audio", "temp_images", "temp_scenes"]:
    os.makedirs(carpeta, exist_ok=True)

def obtener_duracion_audio(archivo_audio):
    comando = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {archivo_audio}"
    duracion = subprocess.check_output(comando, shell=True)
    return float(duracion.strip())

def crear_imagen(texto, color, ruta):
    img = Image.new('RGB', (1920, 1080), color=color)
    d = ImageDraw.Draw(img)
    d.text((100, 500), texto, fill="#ffffff")
    img.save(ruta)

def crear_clip(ruta_img, ruta_aud, duracion, ruta_out):
    filtro_zoom = "zoompan=z='zoom+0.0005':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=125,scale=1920:1080"
    comando = (
        f"ffmpeg -y -loop 1 -i {ruta_img} -i {ruta_aud} "
        f"-vf \"{filtro_zoom}\" -c:v libx264 -tune stillimage -c:a aac "
        f"-b:a 192k -pix_fmt yuv420p -t {duracion} {ruta_out}"
    )
    subprocess.run(comando, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# Botón de ejecución
if st.button("🚀 Lanzar Pipeline"):
    if not api_key:
        st.error("Por favor, introduce tu API Key de OpenRouter en la barra lateral.")
    else:
        barra_progreso = st.progress(0)
        texto_estado = st.empty()
        
        # 1. Llamada a Qwen3.7-Max para generar el Guión y Estructura
        texto_estado.text("Qwen3.7-Max está razonando y generando el guión...")
        
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        
        prompt_sistema = (
            "Actúas como un guionista profesional de documentales históricos. Tu tarea es estructurar un "
            "video corto de 1 minuto sobre el tema que te dará el usuario. Debes dividir el video en exactamente 5 bloques. "
            "Debes responder EXCLUSIVAMENTE con un array JSON válido, sin textos introductorios ni bloques de código markdown. "
            "Cada objeto del array debe contener exactamente las siguientes llaves:\n"
            "- id: entero consecutivo\n"
            "- texto: la narración en español que leerá el locutor (unos 10-12 segundos de lectura)\n"
            "- color: un código hexadecimal oscuro representativo de la atmósfera visual\n"
            "- visual: un prompt detallado en inglés para una IA generadora de imágenes hiperrealista."
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
            
            # Limpiar posibles bloques markdown del output
            raw_content = response.choices[0].message.content.strip()
            if raw_content.startswith("```json"):
                raw_content = raw_content.replace("```json", "").replace("```", "").strip()
            
            ESCENAS_JSON = json.loads(raw_content)
            texto_estado.text("¡Guión estructurado correctamente por Qwen!")
            barra_progreso.progress(20)
            
            # 2. Procesamiento de escenas generadas dinámicamente
            lista_clips = []
            total_escenas = len(ESCENAS_JSON)
            
            for i, escena in enumerate(ESCENAS_JSON):
                id_e = escena["id"]
                texto_estado.text(f"Procesando escena {id_e} de {total_escenas}...")
                
                # Renderizar Audio local
                r_audio = f"temp_audio/audio_{id_e}.mp3"
                tts = gTTS(text=escena["texto"], lang='es', tld='es')
                tts.save(r_audio)
                dur = obtener_duracion_audio(r_audio)
                
                # Renderizar Imagen local placeholder usando el prompt visual de Qwen
                r_imagen = f"temp_images/imagen_{id_e}.png"
                # Mostramos en pantalla el prompt que ideó Qwen para el MVP
                texto_pantalla = f"Prompt IA: {escena['visual'][:80]}..."
                crear_imagen(texto_pantalla, escena["color"], r_imagen)
                
                # Convertir a video clip parcial
                r_clip = f"temp_scenes/escena_{id_e}.mp4"
                crear_clip(r_imagen, r_audio, dur, r_clip)
                
                lista_clips.append(r_clip)
                barra_progreso.progress(int(20 + ((i + 1) / total_escenas) * 60))
                
            # 3. Concatenación final del video maestro
            texto_estado.text("Ensamblando todas las piezas con FFmpeg...")
            with open("lista_videos.txt", "w") as f:
                for clip in lista_clips:
                    f.write(f"file '{clip}'\n")
                    
            video_final = "resultado_qwen_mvp.mp4"
            comando_final = f"ffmpeg -y -f concat -safe 0 -i lista_videos.txt -c copy {video_final}"
            subprocess.run(comando_final, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if os.path.exists("lista_videos.txt"):
                os.remove("lista_videos.txt")
                
            barra_progreso.progress(100)
            texto_estado.text("¡Documental finalizado!")
            
            # Mostrar resultado en la interfaz
            if os.path.exists(video_final):
                with open(video_final, "rb") as file:
                    st.video(file.read())
                    
                st.download_button(
                    label="Descargar Video .mp4",
                    data=open(video_final, "rb"),
                    file_name="documental_qwen_ia.mp4",
                    mime="video/mp4"
                )
                
        except Exception as e:
            st.error(f"Ocurrió un error al procesar el JSON o la API de Qwen: {e}")
