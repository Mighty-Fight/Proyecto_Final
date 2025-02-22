from flask import Flask, Response
import subprocess
import time

app = Flask(__name__)

# Ajusta los datos de tu RTSP (usuario, contraseña, IP, etc.)
rtsp_url = "rtsp://admin:abcd1234..@186.119.48.156:554/Streaming/Channels/101"

def generate_frames():
    while True:
        try:
            # ffmpeg con parámetros para reducir buffering
            command = [
                "ffmpeg",
                "-rtsp_transport", "tcp",    # o "udp", según requieras
                "-i", rtsp_url,
                # Opciones de baja latencia / poco buffering
                "-fflags", "nobuffer",
                "-flags", "low_delay",
                "-strict", "experimental",
                "-analyzeduration", "0",
                "-probesize", "32",

                # Salida en formato MPJPEG (con boundary integrado)
                "-f", "mpjpeg",
                # Reduce la calidad si tu ancho de banda es más limitado (valores más altos = menos calidad)
                "-q:v", "5",
                # Baja la resolución (ej. 640x360) para reducir aún más el tamaño de cada frame
                "-s", "640x360",
                # Envía solo 1 fotograma por segundo
                "-r", "1",
                "pipe:1"
            ]

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=10**8
            )

            while True:
                chunk = process.stdout.read(4096)
                if not chunk:
                    raise RuntimeError("No se están recibiendo más datos de FFmpeg.")
                yield chunk

        except Exception as e:
            print(f"Error: {e}. Reintentando en 2 segundos...")
            time.sleep(2)

@app.route('/video_feed')
def video_feed():
    # boundary=ffmpeg (o boundary=frame) depende de cómo FFmpeg forme el stream MPJPEG
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=ffmpeg'
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)

