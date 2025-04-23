import cv2
import os
import time
import base64
import logging
import threading
import requests
import atexit
import signal
import sys

from flask import Flask, Response, jsonify
from datetime import datetime
from inference_sdk import InferenceHTTPClient
from collections import Counter

# === IMPORTS PARA GOOGLE VISION ===
from google.cloud import vision
from google.oauth2 import service_account

# ============= CONFIGURACIÓN GENERAL =============
RTSP_URL = os.getenv("RTSP_URL", "rtsp://admin:abcd1234..@192.168.0.198:554/Streaming/Channels/101")

# ROI donde esperamos encontrar la placa (x, y, w, h)
ROI_COORDS = (400, 600, 600, 400)

# Ajuste de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Cantidad de segundos que deben pasar antes de volver a intentar OCR
COOLDOWN = 10

# Reducir la frecuencia de llamadas al OCR/detección (tiempo de sleep en el loop principal)
DETECTION_LOOP_SLEEP = 0.3  # ~3-4 llamadas por segundo

# ============= CONFIGURACIÓN ROBOFLOW =============
ROBOFLOW_API_KEY = "jE9ZRJhcQmeW0pOj5UQG"
MODEL_ID = "placas-colombia/2"
roboflow_client = InferenceHTTPClient(
    api_url="https://detect.roboflow.com",
    api_key=ROBOFLOW_API_KEY
)

# ============= CONFIGURACIÓN SERVIDOR DE DESTINO =============
UPDATE_ENDPOINT = "http://3.82.125.113/update"

# ============= FLASK APP =============
app = Flask(__name__)

# ============= ESTADO COMPARTIDO (Protegido con lock) =============
shared_state = {
    "frame_original": None,
    "frame_processed": None,
    "last_plate": None,
    "last_plate_timestamp": "--",
    "last_detection_time": 0,  # Marca de tiempo de la última detección/llamada a OCR
    "plate_image": None,
    "ocr_running": False
}
state_lock = threading.Lock()

# ============= FUNCIONES DE LIMPIEZA Y SEÑALES =============
def cleanup():
    logging.info("Cerrando ventanas OpenCV.")
    cv2.destroyAllWindows()

atexit.register(cleanup)

def signal_handler(sig, frame):
    logging.info("Señal recibida (%s). Cerrando todo.", sig)
    cv2.destroyAllWindows()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ============= HILO DE CAPTURA DE FRAMES =============
def capture_frames():
    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        logging.error("No se pudo conectar al stream: %s", RTSP_URL)
        return

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

    logging.info("Hilo de captura iniciado: leyendo frames en tiempo real...")

    while True:
        ret, frame = cap.read()
        if not ret:
            continue
        
        # Aseguramos tamaño 1920x1080 (opcional si ya viene así)
        frame_resized = cv2.resize(frame, (1920, 1080), interpolation=cv2.INTER_CUBIC)

        with state_lock:
            shared_state["frame_original"] = frame_resized.copy()

        time.sleep(0.01)

    cap.release()

# ============= LÓGICA DE DETECCIÓN (Roboflow + Google Vision) =============
def procesar_placa_con_roboflow(roi):
    """
    Llama a Roboflow para detectar placa en 'roi'. Luego hace OCR con Google Vision.
    Aplica cooldown para no saturar la API.
    """
    try:
        # 1) Guardamos ROI en un archivo temporal
        temp_path = "roi_temp.jpg"
        cv2.imwrite(temp_path, roi)

        # 2) Llamada a Roboflow
        result = roboflow_client.infer(temp_path, model_id=MODEL_ID)
        predictions = result.get("predictions", [])
        if not predictions:
            logging.info("No se detectó placa en la ROI.")
            return

        pred = max(predictions, key=lambda p: p["confidence"])
        confidence = pred["confidence"]
        logging.info(f"Placa detectada: confianza {confidence:.3f}")

        # Calculamos bounding box
        x_pred = int(pred["x"] - pred["width"] / 2)
        y_pred = int(pred["y"] - pred["height"] / 2)
        w_pred = int(pred["width"])
        h_pred = int(pred["height"])

        x1 = max(x_pred, 0)
        y1 = max(y_pred, 0)
        x2 = min(x_pred + w_pred, roi.shape[1])
        y2 = min(y_pred + h_pred, roi.shape[0])

        placa_crop = roi[y1:y2, x1:x2]
        if placa_crop.size == 0:
            logging.info("El recorte está vacío. Coordenadas fuera de rango.")
            return

        # 3) COOLDOWN
        now = time.time()
        with state_lock:
            elapsed = now - shared_state["last_detection_time"]
            if elapsed < COOLDOWN:
                logging.info("Aún en cooldown (%.2fs de %.2fs). No llamamos a OCR.", elapsed, COOLDOWN)
                return
            shared_state["last_detection_time"] = now

        # 4) OCR con Google Vision
        texto_ocr = google_vision_ocr(placa_crop).strip().upper()
        if texto_ocr:
            logging.info(f"OCR extrajo: {texto_ocr}")
            with state_lock:
                shared_state["last_plate"] = texto_ocr
                shared_state["last_plate_timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
                shared_state["plate_image"] = placa_crop.copy()

            # Enviamos al servidor
            enviar_a_servidor(texto_ocr, placa_crop)
        else:
            logging.info("OCR no devolvió texto.")

    except Exception as e:
        logging.error("Error procesando placa con Roboflow/OCR: %s", e)
    finally:
        # Liberamos la bandera
        with state_lock:
            shared_state["ocr_running"] = False

def google_vision_ocr(img):
    """
    Envía 'img' a Google Vision para hacer OCR, pasando las credenciales
    directamente en el código sin usar variables de entorno.
    """
    # >>>>> Asegúrate de poner la ruta correcta a tu archivo .json de Service Account <<<<<
    cred_path = r"C:\Users\mateo\Downloads\sincere-concept-455516-s4-f9c13ffc844a.json"

    # Leemos credenciales directamente
    credentials = service_account.Credentials.from_service_account_file(cred_path)

    # Creamos el cliente Vision usando esas credenciales
    client = vision.ImageAnnotatorClient(credentials=credentials)

    # Guardamos la imagen en disco (para subirla)
    temp_ocr_path = "placa_ocr.jpg"
    cv2.imwrite(temp_ocr_path, img)

    with open(temp_ocr_path, "rb") as image_file:
        content = image_file.read()

    # Creamos objeto Image para Vision
    vision_image = vision.Image(content=content)
    response = client.text_detection(image=vision_image)

    if response.error.message:
        logging.error("Error de Vision API: %s", response.error.message)
        return ""

    annotations = response.text_annotations
    if len(annotations) > 0:
        return annotations[0].description  # Primer item => texto completo
    else:
        return ""

def enviar_a_servidor(placa, placa_img):
    """Envía la placa y la imagen en Base64 a tu servidor (3.82.125.113)."""
    try:
        _, buffer = cv2.imencode('.jpg', placa_img)
        jpg_as_text = base64.b64encode(buffer).decode('utf-8')
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        payload = {
            "placa": placa,
            "timestamp": timestamp,
            "frame": jpg_as_text
        }

        resp = requests.post(UPDATE_ENDPOINT, json=payload, timeout=5)
        logging.info("Respuesta de tu servidor: %s", resp.status_code)
    except Exception as e:
        logging.error("Error enviando datos al servidor: %s", e)

# ============= LOOP DE DETECCIÓN PRINCIPAL =============
def detection_loop():
    cv2.namedWindow("Camera", cv2.WINDOW_NORMAL)
    cv2.namedWindow("ROI", cv2.WINDOW_NORMAL)

    while True:
        with state_lock:
            frame = shared_state["frame_original"]

        if frame is None:
            time.sleep(0.05)
            continue

        x, y, w, h = ROI_COORDS
        roi = frame[y:y+h, x:x+w]
        cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 255, 0), 2)

        # Mostramos en ventanas
        cv2.imshow("Camera", frame)
        cv2.imshow("ROI", roi)

        with state_lock:
            if not shared_state["ocr_running"]:
                shared_state["ocr_running"] = True
                threading.Thread(target=procesar_placa_con_roboflow, args=(roi.copy(),), daemon=True).start()

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        # Limitamos la frecuencia de inferencia (para no saturar APIs)
        time.sleep(DETECTION_LOOP_SLEEP)

    cv2.destroyAllWindows()

# ============= ENDPOINTS FLASK =============
@app.route("/video_feed")
def video_feed():
    """Devuelve el stream MJPEG del frame original."""
    def gen():
        while True:
            with state_lock:
                frame = shared_state["frame_original"]
            if frame is not None:
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/processed_feed")
def processed_feed():
    """Devuelve el stream MJPEG del frame con la ROI dibujada."""
    def gen():
        while True:
            with state_lock:
                frame = (shared_state["frame_processed"]
                         if shared_state["frame_processed"] is not None
                         else shared_state["frame_original"])
            if frame is not None:
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/latest_plate")
def latest_plate():
    """Devuelve la última placa detectada y su timestamp."""
    with state_lock:
        plate = shared_state["last_plate"] if shared_state["last_plate"] else "No se ha detectado ninguna placa aún"
        timestamp_plate = shared_state["last_plate_timestamp"]
    return jsonify({
        "plate": plate,
        "timestamp": timestamp_plate
    })

@app.route("/confirmed_plate_image")
def confirmed_plate_image():
    """Devuelve la imagen JPG de la última placa confirmada."""
    with state_lock:
        img = shared_state["plate_image"]
    if img is not None:
        ret, buffer = cv2.imencode('.jpg', img)
        if ret:
            return Response(buffer.tobytes(), mimetype='image/jpeg')
    return "No hay imagen de placa confirmada disponible", 404

# ============= MAIN =============
if __name__ == "__main__":
    # Iniciamos el hilo de captura
    cap_thread = threading.Thread(target=capture_frames, daemon=True)
    cap_thread.start()

    # Iniciamos el hilo de detección
    detect_thread = threading.Thread(target=detection_loop, daemon=True)
    detect_thread.start()

    # Arrancamos Flask
    app.run(host="0.0.0.0", port=5001, debug=False)