from flask import Flask, Response
import cv2
import time
import threading
import os

from inference_sdk import InferenceHTTPClient

# === CONFIGURACIÓN GENERAL ===
RTSP_URL = "rtsp://admin:abcd1234..@192.168.0.198:554/Streaming/Channels/101"
ROI_COORDS = (600, 600, 200, 200)  # (x, y, w, h)

# Inicializa cliente de Roboflow
CLIENT = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key="jE9ZRJhcQmeW0pOj5UQG"
)

# === FLASK APP ===
app = Flask(__name__)

# === FUNCIONES ===
def analizar_roi_con_roboflow(roi_img):
    try:
        temp_path = "temp_roi.jpg"
        cv2.imwrite(temp_path, roi_img)
        result = CLIENT.infer(temp_path, model_id="prueba_1-tnlwa/1")
        predictions = result.get("predictions", [])
        if predictions:
            print("✅ Placa encontrada")
    except Exception as e:
        print(f"❌ Error al analizar con Roboflow: {e}")

def generate_frames():
    cap = cv2.VideoCapture(RTSP_URL)
    if not cap.isOpened():
        print("❌ No se pudo conectar a la cámara.")
        return

    last_check = 0
    cooldown = 3  # Segundos entre detecciones

    while True:
        success, frame = cap.read()
        if not success:
            continue

        # Dibuja el ROI en el frame (opcional para debug)
        x, y, w, h = ROI_COORDS
        roi = frame[y:y+h, x:x+w]
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 255), 2)

        # Analiza cada 'cooldown' segundos
        if time.time() - last_check > cooldown:
            threading.Thread(target=analizar_roi_con_roboflow, args=(roi.copy(),), daemon=True).start()
            last_check = time.time()

        # Encode y yield para mostrar en el navegador
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue

        frame_bytes = buffer.tobytes()
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")

# === ENDPOINTS FLASK ===
@app.route("/video_feed")
def video_feed():
    return Response(generate_frames(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

# === MAIN ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)