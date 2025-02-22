import ffmpeg
import numpy as np
import cv2
import time

# URL RTSP de la cámara IP
rtsp_url = "rtsp://admin:abcd1234..@181.236.157.101:554/Streaming/Channels/101"

# Ruta completa al archivo ejecutable de FFmpeg
ffmpeg_path = r"C:\ffmpeg\ffmpeg.exe"

# Configura el tamaño de la ventana y la resolución correcta
width, height = 1280, 720

def start_ffmpeg_process():
    """Inicia el proceso de ffmpeg para la transmisión RTSP."""
    return (
        ffmpeg
        .input(rtsp_url)
        .output('pipe:', format='rawvideo', pix_fmt='bgr24')
        .run_async(pipe_stdout=True, cmd=ffmpeg_path)  # Especifica el ejecutable de FFmpeg
    )

# Inicia el proceso de ffmpeg
process = start_ffmpeg_process()

while True:
    try:
        # Leer la cantidad de bytes necesarios para un cuadro de video
        in_bytes = process.stdout.read(width * height * 3)
        if not in_bytes:
            raise ValueError("No se pudo obtener el frame.")
        
        # Convertir los bytes a una imagen en formato numpy
        frame = np.frombuffer(in_bytes, np.uint8).reshape([height, width, 3])
        
        # Mostrar el frame
        cv2.imshow("Transmisión en Vivo", frame)
        
        # Salir al presionar 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    except Exception as e:
        print(f"Error: {e}. Reintentando en 5 segundos...")
        process.terminate()
        time.sleep(5)
        process = start_ffmpeg_process()

# Cerrar el proceso y la ventana de OpenCV
process.terminate()
cv2.destroyAllWindows()
