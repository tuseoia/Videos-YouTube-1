import streamlit as st
import os
import subprocess
from gtts import gTTS
from PIL import Image, ImageDraw

# Configuración inicial de la página
st.set_page_config(page_title="IA Video Generator", page_icon="🎬", layout="centered")

st.title("🎬 Generador Automatizado de Documentales")
st.write("Prototipo funcional (MVP) de 1 minuto que genera audio, imágenes dinámicas y video de forma local.")

# Datos de prueba simulados (Mock Data)
ESCENAS_JSON = [
    {"id": 1, "texto": "Bienvenidos a Bilbao. Lo que hoy es una metrópoli moderna, comenzó siendo un humilde pueblo de pescadores.", "color": "#1a2a3a", "visual": ""},
    {"id": 2, "texto": "El destino de la villa cambió radicalmente en el siglo diecinueve gracias al descubrimiento del hierro.", "color": "#4a1a1a", "visual": ""},
    {"id": 3, "texto": "Grandes altos hornos comenzaron a dominar el horizonte, transformando el mineral en acero puro.", "color": "#2d3e2d", "visual": ""},
    {"id": 4, "texto": "A pesar de las crisis y las inundaciones, el carácter de su pueblo se mantuvo inquebrantable.", "color": "#3a3a3a", "visual": ""},
    {"id": 5, "texto": "Hoy, el titanio del Museo Guggenheim brilla como símbolo de una ciudad que supo resurgir de sus cenizas.", "color": "#1c3334", "visual": ""}
]

# Inputs en la interfaz de usuario
tema = st.text_input("Tema del documental:", "El Milagro de Bilbao")
duracion = st.selectbox("Duración del video:", ["1 Minuto (Modo MVP)", "30 Minutos (Requiere API)", "50 Minutos (Requiere API)"])

# Asegurar que existan carpetas temporales limpias
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

# Botón ejecutor
if st.button("🚀 Comenzar Generación"):
    barra_progreso = st.progress(0)
    texto_estado = st.empty()
    
    lista_clips = []
    total_escenas = len(ESCENAS_JSON)
    
    for i, escena in enumerate(ESCENAS_JSON):
        id_e = escena["id"]
        texto_estado.text(f"Procesando escena {id_e} de {total_escenas}...")
        
        # 1. Audio
        r_audio = f"temp_audio/audio_{id_e}.mp3"
        tts = gTTS(text=escena["texto"], lang='es', tld='es')
        tts.save(r_audio)
        dur = obtener_duracion_audio(r_audio)
        
        # 2. Imagen
        r_imagen = f"temp_images/imagen_{id_e}.png"
        crear_imagen(escena["visual"], escena["color"], r_imagen)
        
        # 3. Clip de video parcial
        r_clip = f"temp_scenes/escena_{id_e}.mp4"
        crear_clip(r_imagen, r_audio, dur, r_clip)
        
        lista_clips.append(r_clip)
        barra_progreso.progress(int(((i + 1) / total_escenas) * 80))
        
    # 4. Concatenación final
    texto_estado.text("Ensamblando todas las escenas...")
    with open("lista_videos.txt", "w") as f:
        for clip in lista_clips:
            f.write(f"file '{clip}'\n")
            
    video_final = "resultado_mvp.mp4"
    comando_final = f"ffmpeg -y -f concat -safe 0 -i lista_videos.txt -c copy {video_final}"
    subprocess.run(comando_final, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Limpieza
    if os.path.exists("lista_videos.txt"):
        os.remove("lista_videos.txt")
        
    barra_progreso.progress(100)
    texto_estado.text("¡Video renderizado con éxito!")
    
    # Mostrar el reproductor de video en la web
    if os.path.exists(video_final):
        with open(video_final, "rb") as file:
            st.video(file.read())
            
        st.download_button(
            label="Descargar Video .mp4",
            data=open(video_final, "rb"),
            file_name="documental_ia_mvp.mp4",
            mime="video/mp4"
        )
