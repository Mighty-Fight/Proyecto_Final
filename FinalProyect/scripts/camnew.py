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

# === CONFIGURACIÓN (vía variables de entorno o valores por defecto) ===
RTSP_URL = os.getenv("RTSP_URL", "rtsp://admin:abcd1234..@181.236.149.17:554/Streaming/Channels/101")
ROI_COORDS = (520, 120, 400, 400)
TESSERACT_CMD = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

PLATE_DISAPPEAR_TIMEOUT = 60  # segundos
NUM_SAMPLES = 9  # Número de muestras OCR a realizar para confirmar la placa

# === CONFIGURACIÓN DEL LOGGING ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# === FLASK APP ===
app = Flask(__name__)

# === ESTADO COMPARTIDO (protegido por lock) ===
state_lock = threading.Lock()
shared_state = {
    "frame_original": None,
    "frame_processed": None,
    "confirmed_plate": "",
    "last_plate_timestamp": "--",
    "last_plate": None,
    "last_detection_time": 0,
    "last_seen_time": 0,
    "confirmed_plate_image": None  # Imagen de la placa confirmada (procesada)
}

def timestamp_bogota():
    bogota = pytz.timezone("America/Bogota")
    return datetime.now(bogota).strftime("%Y-%m-%d %H:%M:%S")

def detectar_por_color(roi):
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    blanco = cv2.inRange(hsv, (0, 0, 170), (180, 60, 255))
    amarillo = cv2.inRange(hsv, (15, 50, 150), (35, 255, 255))
    total = roi.shape[0] * roi.shape[1]
    return (cv2.countNonZero(blanco) / total) > 0.2 or (cv2.countNonZero(amarillo) / total) > 0.2

def detectar_por_forma(roi):
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5,5), 0), 50, 200)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        if cv2.contourArea(cnt) > 800:
            approx = cv2.approxPolyDP(cnt, 0.02 * cv2.arcLength(cnt, True), True)
            if 4 <= len(approx) <= 6:
                return True
    return False

def order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect

def detectar_placa_desde_imagen(image):
    """
    Procesa la imagen para detectar y extraer la placa.
    Realiza NUM_SAMPLES lecturas OCR seguidas y, mediante votación mayoritaria,
    confirma la placa si el resultado tiene el formato válido (3 letras y 3 números).
    """
    logging.info("Procesando imagen para OCR...")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5,5), 0), 50, 200)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    plate_candidate = None
    max_area = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 1000 and area > max_area:
            max_area = area
            plate_candidate = cnt
    if plate_candidate is None:
        return

    approx = cv2.approxPolyDP(plate_candidate, 0.02 * cv2.arcLength(plate_candidate, True), True)
    if len(approx) != 4:
        x, y, w, h = cv2.boundingRect(plate_candidate)
        rect = order_points(np.array([[x, y], [x+w, y], [x+w, y+h], [x, y+h]], dtype="float32"))
    else:
        rect = order_points(approx.reshape(4, 2))

    # Transformación de perspectiva para obtener la imagen enderezada de la placa
    W, H = 300, 100
    dst = np.array([[0, 0], [W-1, 0], [W-1, H-1], [0, H-1]], dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (W, H))

    # Recortar márgenes para eliminar bordes no deseados
    margin_x = 3
    margin_y_top = 10
    margin_y_bottom = 20
    cropped = warped[margin_y_top:H-margin_y_bottom, margin_x:W-margin_x]
    scaled = cv2.resize(cropped, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    # Realizar múltiples lecturas OCR de forma local
    config = "--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    lecturas = []
    for _ in range(NUM_SAMPLES):
        resultado = "".join(c for c in pytesseract.image_to_string(scaled, config=config).strip() if c.isalnum()).upper()
        lecturas.append(resultado)
    logging.info("Múltiples lecturas OCR: %s", lecturas)

    filtrado = Counter(lecturas).most_common(1)[0][0]
    letras = "".join(c for c in filtrado if c.isalpha())
    numeros = "".join(c for c in filtrado if c.isdigit())
    logging.info("Resultado filtrado: Letras: %s, Números: %s", letras, numeros)

    if len(letras) == 3 and len(numeros) == 3:
        placa = f"{letras}{numeros}"
        current_time = time.time()
        with state_lock:
            if placa == shared_state["last_plate"] and (current_time - shared_state["last_seen_time"]) < PLATE_DISAPPEAR_TIMEOUT:
                shared_state["last_seen_time"] = current_time
                logging.info("Placa repetida detectada, sin actualización: %s", placa)
                return
            # Actualizar estado con la nueva placa confirmada y guardar la imagen final
            shared_state["last_plate"] = placa
            shared_state["last_seen_time"] = current_time
            shared_state["last_detection_time"] = current_time
            shared_state["last_plate_timestamp"] = timestamp_bogota()
            shared_state["confirmed_plate"] = placa
            shared_state["confirmed_plate_image"] = scaled.copy()

        logging.info("Placa confirmada: %s (%s)", placa, shared_state["last_plate_timestamp"])
        try:
            requests.post("http://44.211.67.168/update", json={
                "placa": placa,
                "timestamp": shared_state["last_plate_timestamp"]
            }, timeout=5)
        except Exception as e:
            logging.error("Error al enviar POST al servidor: %s", e)
    else:
        logging.info("Formato de lectura inválido en la muestra: %s", filtrado)

def main_loop():
    cap = cv2.VideoCapture(RTSP_URL)
    if not cap.isOpened():
        logging.error("No se pudo conectar al stream.")
        return
    logging.info("Stream conectado. Procesando en tiempo real...")

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        with state_lock:
            shared_state["frame_original"] = frame.copy()
        # Dibujar la ROI para visualización
        x, y, w, h = ROI_COORDS
        roi = frame[y:y+h, x:x+w]
        cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 255, 0), 2)
        with state_lock:
            shared_state["frame_processed"] = frame.copy()

        # Si en la ROI se detecta posible placa, se procesa el frame actual
        if detectar_por_color(roi) or detectar_por_forma(roi):
            detectar_placa_desde_imagen(frame)
        # Breve pausa para mantener alta tasa de procesamiento sin saturar la CPU
        time.sleep(0.005)

# === FLASK ENDPOINTS ===
@app.route("/video_feed")
def video_feed():
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
    with state_lock:
        plate = shared_state["confirmed_plate"] if shared_state["confirmed_plate"] else "No se ha detectado ninguna placa aún"
        timestamp_plate = shared_state["last_plate_timestamp"]
    return jsonify({
        "plate": plate,
        "timestamp": timestamp_plate
    })

@app.route("/confirmed_plate_image")
def confirmed_plate_image():
    with state_lock:
        img = shared_state["confirmed_plate_image"]
    if img is not None:
        ret, buffer = cv2.imencode('.jpg', img)
        if ret:
            return Response(buffer.tobytes(), mimetype='image/jpeg')
    return "No hay imagen de placa confirmada disponible", 404

if __name__ == "__main__":
    detection_thread = threading.Thread(target=main_loop, daemon=True)
    detection_thread.start()
    app.run(host="0.0.0.0", port=5001, debug=False)
