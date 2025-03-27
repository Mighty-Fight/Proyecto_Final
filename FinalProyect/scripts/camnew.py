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

# === CONFIGURACIÓN (vía variables de entorno o valores por defecto) ===
RTSP_URL = os.getenv("RTSP_URL", "rtsp://admin:abcd1234..@181.236.149.17:554/Streaming/Channels/101")

# ROI donde esperamos encontrar la placa. Ajusta estas coordenadas:
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
shared_state = {
    "frame_original": None,
    "frame_processed": None,
    "confirmed_plate": "",
    "last_plate_timestamp": "--",
    "last_plate": None,
    "last_detection_time": 0,
    "last_seen_time": 0,
    "confirmed_plate_image": None,  # Imagen de la placa confirmada (procesada)
    "ocr_candidate_image": None,      # Imagen candidata que se procesa para OCR
    "ocr_running": False              # Bandera para evitar múltiples procesos OCR simultáneos
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

# === FUNCIONES DE PROCESAMIENTO ===
def timestamp_bogota():
    """Devuelve un string con la fecha/hora actual en zona horaria de Bogotá."""
    bogota = pytz.timezone("America/Bogota")
    return datetime.now(bogota).strftime("%Y-%m-%d %H:%M:%S")

def order_points(pts):
    """Ordena los 4 puntos de un rectángulo en el siguiente orden:
       [top-left, top-right, bottom-right, bottom-left]."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect

def detectar_placa_por_forma(image):
    """
    1) Convierte a gris y aplica Canny.
    2) Busca contornos y aproxima polígonos.
    3) Selecciona el contorno que sea un rectángulo con área suficiente y
       con un aspect ratio compatible con placas (p.ej. 1.5 a 3.5).
    4) Aplica transformación de perspectiva para normalizar la imagen.
    5) Devuelve la imagen transformada si se encuentra, de lo contrario None.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 200)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    plate_img = None
    max_area = 0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 1000:
            continue  # Ignorar contornos muy pequeños

        approx = cv2.approxPolyDP(cnt, 0.02 * cv2.arcLength(cnt, True), True)
        if len(approx) == 4:  # Buscamos un rectángulo
            x, y, w, h = cv2.boundingRect(approx)
            ratio = w / float(h)
            if 1.5 < ratio < 3.5 and area > max_area:
                max_area = area
                plate_img = approx

    if plate_img is None:
        return None

    # Transformación de perspectiva
    rect = order_points(plate_img.reshape(4, 2))
    W, H = 300, 100  # Tamaño normalizado
    dst = np.array([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (W, H))
    return warped

def realizar_ocr_y_confirmar_placa(warped):
    """
    Realiza el OCR de la imagen ya recortada de la placa.
    Usa múltiples lecturas para una votación mayoritaria y valida 3 letras + 3 números.
    Actualiza el estado compartido si la placa es válida.
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

    # Validación: 3 letras + 3 dígitos (placa típica colombiana)
    if len(letras) == 3 and len(numeros) == 3:
        placa = f"{letras}{numeros}"
        current_time = time.time()

        with state_lock:
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

        try:
            requests.post("http://44.211.67.168/update", json={
                "placa": placa,
                "timestamp": shared_state["last_plate_timestamp"]
            }, timeout=5)
        except Exception as e:
            logging.error("Error al enviar POST al servidor: %s", e)
    else:
        logging.info("Formato de lectura inválido en la muestra: %s", filtrado)

def rotate_image(image, angle):
    """Rota la imagen en el ángulo especificado."""
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(image, M, (w, h))
    return rotated

def procesar_placa(roi):
    """
    Función que procesa la región de interés en un hilo aparte.
    Se intenta detectar la placa de forma normal y, si falla, se prueban diferentes ángulos.
    Al finalizar se libera la bandera de OCR.
    """
    try:
        warped_plate = detectar_placa_por_forma(roi)
        # Si no se detecta, intenta con rotaciones para soportar diferentes ángulos
        if warped_plate is None:
            for angle in [-15, 15, -30, 30]:
                rotated = rotate_image(roi, angle)
                warped_plate = detectar_placa_por_forma(rotated)
                if warped_plate is not None:
                    logging.info("Placa detectada con rotación de %d grados", angle)
                    break
        if warped_plate is not None:
            realizar_ocr_y_confirmar_placa(warped_plate)
    finally:
        with state_lock:
            shared_state["ocr_running"] = False

def capture_frames():
    """
    Hilo dedicado a la captura continua de frames desde el stream RTSP.
    Se configura el VideoCapture para intentar reducir el tamaño del buffer y
    se actualiza constantemente la variable compartida "frame_original" con el frame más reciente.
    """
    cap = cv2.VideoCapture(RTSP_URL)
    if not cap.isOpened():
        logging.error("No se pudo conectar al stream.")
        return
    # Intentar reducir el buffer (nota: no todos los backends lo soportan)
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
    Hilo dedicado al procesamiento y detección usando el frame más reciente capturado.
    Extrae la ROI, dibuja la misma, y lanza la detección y OCR en un hilo separado
    solo si no hay otro proceso OCR en curso.
    """
    while True:
        with state_lock:
            frame = shared_state["frame_original"]
        if frame is None:
            continue

        # Extraer ROI donde se espera la placa
        x, y, w, h = ROI_COORDS
        roi = frame[y:y+h, x:x+w]

        # Dibujar la ROI en el frame (para la ventana "Camera")
        frame_with_roi = frame.copy()
        cv2.rectangle(frame_with_roi, (x, y), (x+w, y+h), (255, 255, 0), 2)

        with state_lock:
            shared_state["frame_processed"] = frame_with_roi.copy()

        # Solo se lanza un proceso OCR si no hay otro en curso
        with state_lock:
            if not shared_state["ocr_running"]:
                shared_state["ocr_running"] = True
                threading.Thread(target=procesar_placa, args=(roi,)).start()

        # Mostrar ventanas emergentes (se mantienen para debug/confirmación)
        cv2.imshow("Camera", frame_with_roi)
        with state_lock:
            ocr_img = shared_state["ocr_candidate_image"]
        if ocr_img is not None:
            cv2.imshow("OCR", ocr_img)
        else:
            cv2.imshow("OCR", np.zeros((200, 400, 3), dtype=np.uint8))

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        time.sleep(0.005)
    cv2.destroyAllWindows()

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
    # Iniciamos el hilo de captura de frames
    cap_thread = threading.Thread(target=capture_frames, daemon=True)
    cap_thread.start()
    # Iniciamos el hilo de detección/procesamiento
    detect_thread = threading.Thread(target=detection_loop, daemon=True)
    detect_thread.start()
    # Ejecutamos la app Flask
    app.run(host="0.0.0.0", port=5001, debug=False)
