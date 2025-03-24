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

# === CONFIGURACIÓN ===
rtsp_url = "rtsp://admin:abcd1234..@181.236.141.192:554/Streaming/Channels/101"
roi_coords = (520, 120, 400, 400)
pytesseract.pytesseract.tesseract_cmd = "/usr/local/bin/tesseract" #INSTANCIA
#pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe" #LOCAL




# === FLASK ===
app = Flask(__name__)
frame_original = None
frame_processed = None
latest_temp_image = None

# === ESTADO ===
last_plate = None
last_detection_time = 0
last_seen_time = 0
last_plate_timestamp = "--"
confirmed_plate = ""
PLATE_DISAPPEAR_TIMEOUT = 60  # segundos

# === FUNCIONES ===
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
    s, diff = pts.sum(axis=1), np.diff(pts, axis=1)
    rect[0], rect[2] = pts[np.argmin(s)], pts[np.argmax(s)]
    rect[1], rect[3] = pts[np.argmin(diff)], pts[np.argmax(diff)]
    return rect

def detectar_placa_desde_imagen(image):
    global last_plate, last_detection_time, last_seen_time, last_plate_timestamp, confirmed_plate

    print("OCR iniciado desde imagen temporal...")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 200)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    plate_candidate = max((cnt for cnt in contours if cv2.contourArea(cnt) > 1000), default=None, key=cv2.contourArea)
    if plate_candidate is None:
        return

    approx = cv2.approxPolyDP(plate_candidate, 0.02 * cv2.arcLength(plate_candidate, True), True)
    if len(approx) != 4:
        x, y, w, h = cv2.boundingRect(plate_candidate)
        rect = order_points(np.array([[x, y], [x+w, y], [x+w, y+h], [x, y+h]], dtype="float32"))
    else:
        rect = order_points(approx.reshape(4, 2))

    W, H = 300, 100
    M = cv2.getPerspectiveTransform(rect, np.array([[0, 0], [W-1, 0], [W-1, H-1], [0, H-1]], dtype="float32"))
    warped = cv2.warpPerspective(image, M, (W, H))
    margin_x = 15  # píxeles a recortar de izquierda y derecha
    margin_y_top = 10  # píxeles a recortar desde arriba
    margin_y_bottom = 20  # píxeles a recortar desde abajo

    cropped = warped[margin_y_top:H - margin_y_bottom, margin_x:W - margin_x]

    scaled = cv2.resize(cropped, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    config = "--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    lecturas = [
        "".join(c for c in pytesseract.image_to_string(scaled, config=config).strip() if c.isalnum()).upper()
        for _ in range(9)
    ]
    lecturas = [l for l in lecturas if l]
    print("OCR múltiples lecturas:", lecturas)
    if not lecturas:
        return

    filtrado = Counter(lecturas).most_common(1)[0][0]
    letras = "".join(c for c in filtrado if c.isalpha())
    numeros = "".join(c for c in filtrado if c.isdigit())

    if len(letras) == 3 and len(numeros) == 3:
        placa = f"{letras}{numeros}"
        current_time = time.time()
        if placa == last_plate and (current_time - last_seen_time) < PLATE_DISAPPEAR_TIMEOUT:
            last_seen_time = current_time
            print(f"Placa repetida ignorada: {placa}")
            return
        last_plate = placa
        last_seen_time = current_time
        last_detection_time = current_time
        last_plate_timestamp = timestamp_bogota()
        confirmed_plate = placa
        print(f"Placa detectada: {placa} ({last_plate_timestamp})")

        # POST al servidor Node.js
        try:
            requests.post("http://44.211.67.168/update", json={
                "placa": confirmed_plate,
                "timestamp": last_plate_timestamp
            })
        except Exception as e:
            print(f"Error al enviar POST al servidor: {e}")
    else:
        print("Lectura ignorada por formato inválido")

# === LOOP PRINCIPAL ===
def main_loop():
    global frame_original, frame_processed, latest_temp_image
    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        raise RuntimeError("No se pudo conectar al stream.")
    print("CAMNEW: Stream conectado. Procesando en tiempo real...")

    while True:
        ret, frame = cap.read()
        if not ret:
            continue
        frame_original = frame.copy()
        x, y, w, h = roi_coords
        roi = frame[y:y+h, x:x+w]
        cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 255, 0), 2)
        frame_processed = frame.copy()

        if detectar_por_color(roi) or detectar_por_forma(roi):
            print("Posible placa detectada. Guardando imagen temporal...")
            latest_temp_image = frame.copy()
            detectar_placa_desde_imagen(latest_temp_image)
        time.sleep(0.01)

# === FLASK ENDPOINTS ===
@app.route("/video_feed")
def video_feed():
    def gen():
        while True:
            if frame_original is not None:
                ret, buffer = cv2.imencode('.jpg', frame_original)
                if ret:
                    yield (b"--frame\r\n"
                           b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/processed_feed")
def processed_feed():
    def gen():
        while True:
            if frame_processed is not None:
                ret, buffer = cv2.imencode('.jpg', frame_processed)
                if ret:
                    yield (b"--frame\r\n"
                           b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/latest_plate")
def latest_plate():
    return jsonify({
        "plate": confirmed_plate if confirmed_plate else "No se ha detectado ninguna placa aún",
        "timestamp": last_plate_timestamp
    })

# === INICIAR ===
if __name__ == "__main__":
    threading.Thread(target=main_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5001, debug=False)
