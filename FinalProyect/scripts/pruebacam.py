import cv2
import numpy as np
import pytesseract
import pytz
import time
import threading
from datetime import datetime
from collections import Counter
from flask import Flask, Response, jsonify
import requests
import logging
import os
import signal
import sys
import atexit
import base64

from inference_sdk import InferenceHTTPClient

# === CONFIGURACIÓN ROBOFLOW (ajusta con tu API KEY y tu MODEL_ID) ===
CLIENT = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key="jE9ZRJhcQmeW0pOj5UQG"  # <--- Reemplaza aquí con tu clave real
)
MODEL_ID = "itm-mprof/placas-colombia/2"  # o "placas-colombia/2" si aplica

# === CONFIGURACIÓN (vía variables de entorno o valores por defecto) ===
RTSP_URL = os.getenv("RTSP_URL", "rtsp://admin:abcd1234..@192.168.0.198:554/Streaming/Channels/101")

# ROI donde esperamos encontrar la placa (x, y, ancho, alto)
ROI_COORDS = (500, 600, 300, 300)

TESSERACT_CMD = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

PLATE_DISAPPEAR_TIMEOUT = 60  # segundos para no re-declarar la misma placa
NUM_SAMPLES = 9            # Número de muestras OCR a realizar para confirmar la placa

# === CONFIGURACIÓN DEL LOGGING ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# === FLASK APP ===
app = Flask(__name__)

# === ESTADO COMPARTIDO (protegido por lock) ===
shared_state = {
    "frame_original": None,
    "frame_processed": None,
    "confirmed_plate": "",
    "last_plate_timestamp": "--",
    "last_plate": None,
    "last_detection_time": 0,
    "last_seen_time": 0,
    "confirmed_plate_image": None,  # Imagen de la placa confirmada (procesada)
    "ocr_candidate_image": None,    # Imagen candidata que se procesa para OCR
    "ocr_running": False            # Bandera para evitar múltiples procesos OCR simultáneos
}
state_lock = threading.Lock()

# === FUNCIONES DE LIMPIEZA AL SALIR ===
def cleanup():
    logging.info("Ejecutando función de limpieza: cerrando ventanas OpenCV.")
    cv2.destroyAllWindows()

atexit.register(cleanup)

def signal_handler(sig, frame):
    logging.info("Señal recibida (%s). Cerrando ventanas y finalizando proceso.", sig)
    cv2.destroyAllWindows()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ====================================================================================
# ===========================   FUNCIONES DE PROCESAMIENTO   ==========================
# ====================================================================================

def timestamp_bogota():
    """Devuelve un string con la fecha/hora actual en zona horaria de Bogotá."""
    bogota = pytz.timezone("America/Bogota")
    return datetime.now(bogota).strftime("%Y-%m-%d %H:%M:%S")

def rotate_image(image, angle):
    """Rota la imagen en el ángulo especificado (para pruebas si hiciera falta)."""
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(image, M, (w, h))
    return rotated

def realizar_ocr_y_confirmar_placa(warped):
    """
    Realiza el OCR de la imagen ya recortada de la placa.
    - Múltiples lecturas para una votación mayoritaria
    - Valida 3 letras + 3 números (placas típicas en Colombia)
    - Actualiza estado compartido si la placa es válida
    - Envía la placa confirmada al servidor Node.js (ruta /update) con la imagen en Base64
    """
    H, W, _ = warped.shape
    margin_x = 5
    margin_y_top = 5
    margin_y_bottom = 5
    cropped = warped[margin_y_top:H - margin_y_bottom, margin_x:W - margin_x]
    scaled = cv2.resize(cropped, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    # Guardamos la imagen candidata para mostrar en la ventana OCR
    with state_lock:
        shared_state["ocr_candidate_image"] = scaled.copy()

    # Config para Tesseract (solo letras/números, psm=7)
    config = "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    lecturas = []
    for _ in range(NUM_SAMPLES):
        resultado = pytesseract.image_to_string(scaled, config=config).strip()
        resultado = "".join(c for c in resultado if c.isalnum()).upper()
        lecturas.append(resultado)

    logging.info("Múltiples lecturas OCR: %s", lecturas)
    if not lecturas:
        return

    filtrado = Counter(lecturas).most_common(1)[0][0]
    letras = "".join(c for c in filtrado if c.isalpha())
    numeros = "".join(c for c in filtrado if c.isdigit())
    logging.info("Resultado filtrado: Letras: %s, Números: %s", letras, numeros)

    # Validación: 3 letras + 3 dígitos (placa típica)
    if len(letras) == 3 and len(numeros) == 3:
        placa = f"{letras}{numeros}"
        current_time = time.time()

        with state_lock:
            # Evitar duplicados si no ha pasado PLATE_DISAPPEAR_TIMEOUT
            if placa == shared_state["last_plate"] and (current_time - shared_state["last_seen_time"]) < PLATE_DISAPPEAR_TIMEOUT:
                shared_state["last_seen_time"] = current_time
                logging.info("Placa repetida detectada, sin actualización: %s", placa)
                return

            shared_state["last_plate"] = placa
            shared_state["last_seen_time"] = current_time
            shared_state["last_detection_time"] = current_time
            shared_state["last_plate_timestamp"] = timestamp_bogota()
            shared_state["confirmed_plate"] = placa
            shared_state["confirmed_plate_image"] = scaled.copy()

        logging.info("Placa confirmada: %s (%s)", placa, shared_state["last_plate_timestamp"])

        # Convertir la imagen a Base64
        _, buffer = cv2.imencode('.jpg', scaled)
        jpg_as_text = base64.b64encode(buffer).decode('utf-8')

        # Enviar al servidor Node.js
        try:
            requests.post("http://44.211.67.168/update", json={
                "placa": placa,
                "timestamp": shared_state["last_plate_timestamp"],
                "frame": jpg_as_text
            }, timeout=5)
        except Exception as e:
            logging.error("Error al enviar POST al servidor: %s", e)
    else:
        logging.info("Formato de lectura inválido en la muestra: %s", filtrado)

def detectar_placa_por_roboflow(roi):
    """
    Llama a la API de Roboflow para detectar el bounding box de la placa en la ROI.
    Retorna la imagen recortada (si se detecta) o None.
    """
    # Guardamos temporalmente la ROI
    cv2.imwrite("roi_temp.jpg", roi)

    # Inferencia en Roboflow
    result = CLIENT.infer("roi_temp.jpg", model_id=MODEL_ID)
    predictions = result.get("predictions", [])

    if not predictions:
        return None

    # Tomar la predicción con mayor confianza
    pred = max(predictions, key=lambda p: p["confidence"])
    x_pred = int(pred["x"] - pred["width"] / 2)
    y_pred = int(pred["y"] - pred["height"] / 2)
    w_pred = int(pred["width"])
    h_pred = int(pred["height"])

    # Asegurar que no exceda los límites de ROI
    x1 = max(x_pred, 0)
    y1 = max(y_pred, 0)
    x2 = min(x_pred + w_pred, roi.shape[1])
    y2 = min(y_pred + h_pred, roi.shape[0])

    recorte = roi[y1:y2, x1:x2]
    return recorte

def procesar_placa(roi):
    """
    Función que procesa la región de interés en un hilo aparte.
    1) Llama a Roboflow para obtener bounding box.
    2) Realiza OCR del recorte y confirma placa.
    Al finalizar se libera la bandera de OCR.
    """
    try:
        recorte_placa = detectar_placa_por_roboflow(roi)
        if recorte_placa is not None:
            logging.info("Placa detectada por Roboflow. Tamaño recorte: %s", recorte_placa.shape)
            # Llamamos a realizar_ocr_y_confirmar_placa
            realizar_ocr_y_confirmar_placa(recorte_placa)
        else:
            logging.info("No se detectaron placas en la ROI.")
    except Exception as e:
        logging.error(f"Error en procesar_placa: {e}")
    finally:
        with state_lock:
            shared_state["ocr_running"] = False

# ====================================================================================
# ===========================    HILOS DE CAPTURA Y DETECCIÓN   =======================
# ====================================================================================

def capture_frames():
    """
    Hilo dedicado a la captura continua de frames desde el stream RTSP.
    Actualiza la variable compartida "frame_original" con el frame más reciente.
    """
    cap = cv2.VideoCapture(RTSP_URL)
    if not cap.isOpened():
        logging.error("No se pudo conectar al stream RTSP.")
        return

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    logging.info("Capture thread iniciado, leyendo frames en tiempo real...")

    while True:
        ret, frame = cap.read()
        if not ret:
            continue
        with state_lock:
            shared_state["frame_original"] = frame.copy()
    cap.release()

def detection_loop():
    """
    Hilo dedicado al procesamiento y detección usando el frame más reciente.
    - Extrae la ROI
    - Lanza la detección (via Roboflow) y OCR en un hilo separado
      solo si no hay otro proceso OCR en curso.
    """
    detection_cooldown = 5  # segundos entre intentos
    last_detection_time = 0

    while True:
        with state_lock:
            frame = shared_state["frame_original"]
        if frame is None:
            time.sleep(0.1)
            continue

        # Extraer ROI
        x, y, w, h = ROI_COORDS
        roi = frame[y:y+h, x:x+w]

        # Dibujar ROI en el frame
        frame_with_roi = frame.copy()
        cv2.rectangle(frame_with_roi, (x, y), (x+w, y+h), (255, 255, 0), 2)

        with state_lock:
            shared_state["frame_processed"] = frame_with_roi.copy()

        # Control de cooldown
        if time.time() - last_detection_time > detection_cooldown:
            with state_lock:
                if not shared_state["ocr_running"]:
                    shared_state["ocr_running"] = True
                    threading.Thread(target=procesar_placa, args=(roi,)).start()
                    last_detection_time = time.time()

        # Mostrar ventanas emergentes (para debug o supervisión)
        cv2.imshow("Camera", frame_with_roi)
        with state_lock:
            ocr_img = shared_state["ocr_candidate_image"]
        if ocr_img is not None:
            cv2.imshow("OCR", ocr_img)
        else:
            cv2.imshow("OCR", np.zeros((200, 400, 3), dtype=np.uint8))

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        time.sleep(0.01)

    cv2.destroyAllWindows()

# ====================================================================================
# ===========================    FLASK ENDPOINTS    ==================================
# ====================================================================================

@app.route("/video_feed")
def video_feed():
    """Devuelve el video original en formato MJPEG."""
    def gen():
        while True:
            with state_lock:
                frame = shared_state["frame_original"]
            if frame is not None:
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    yield (b"--frame\r\n"
                           b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/processed_feed")
def processed_feed():
    """Devuelve el video con la ROI dibujada en formato MJPEG."""
    def gen():
        while True:
            with state_lock:
                frame = shared_state["frame_processed"]
            if frame is not None:
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    yield (b"--frame\r\n"
                           b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/latest_plate")
def latest_plate():
    """Devuelve la última placa confirmada y su timestamp."""
    with state_lock:
        plate = shared_state["confirmed_plate"] if shared_state["confirmed_plate"] else "No se ha detectado ninguna placa aún"
        timestamp_plate = shared_state["last_plate_timestamp"]
    return jsonify({
        "plate": plate,
        "timestamp": timestamp_plate
    })

@app.route("/confirmed_plate_image")
def confirmed_plate_image():
    """Devuelve la imagen de la última placa confirmada."""
    with state_lock:
        img = shared_state["confirmed_plate_image"]
    if img is not None:
        ret, buffer = cv2.imencode('.jpg', img)
        if ret:
            return Response(buffer.tobytes(), mimetype='image/jpeg')
    return "No hay imagen de placa confirmada disponible", 404

# ====================================================================================
# ===========================       MAIN (arranque)     ==============================
# ====================================================================================

if __name__ == "__main__":
    # Iniciamos el hilo de captura de frames
    cap_thread = threading.Thread(target=capture_frames, daemon=True)
    cap_thread.start()

    # Iniciamos el hilo de detección/procesamiento
    detect_thread = threading.Thread(target=detection_loop, daemon=True)
    detect_thread.start()

    # Ejecutamos la app Flask
    app.run(host="0.0.0.0", port=5001, debug=False)
