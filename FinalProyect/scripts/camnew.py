import cv2
import numpy as np
import pytesseract
import threading
import queue
import time
from collections import Counter
from flask import Flask, Response
import requests

app = Flask(__name__)

# ===============================
# Configuración Tesseract
# ===============================
pytesseract.pytesseract.tesseract_cmd = r"/usr/local/bin/tesseract"
# Para Windows, usa:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ===============================
# Parámetros de la cámara y ROI
# ===============================
rtsp_url = "rtsp://admin:abcd1234..@181.236.129.6:554/Streaming/Channels/101"
width, height = 1280, 720
roi_x, roi_y, roi_w, roi_h = 400, 200, 500, 200

# ===============================
# Cola y variables para OCR
# Se usa una cola con maxsize=1 para procesar siempre el último frame
# ===============================
ocr_queue = queue.Queue(maxsize=1)
number_samples = []
letter_samples = []
sample_limit = 3

confirmed_plate = ""  # Placa confirmada final
pending_plate = ""    # Placa pendiente
pending_count = 0
confirmation_threshold = 2

# Variables para cooldown
last_confirmed_time = 0
cooldown_seconds = 5  # Tiempo de inactividad para ignorar la misma placa

# ===============================
# Variables para los streams
# ===============================
frame_original = None
frame_processed = None

##############################################
# Función para enviar la placa al servidor
##############################################
def send_plate_to_server(plate):
    try:
        requests.post('http://eurowash.ddns.net/update', json={'placa': plate}, timeout=5)
        print(f"[INFO] Placa '{plate}' enviada al servidor.")
    except Exception as e:
        print(f"[ERROR] Al enviar la placa: {e}")

##############################################
# Funciones de preprocesamiento
##############################################
def advanced_preprocessing(image_bgr):
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    adapt = cv2.adaptiveThreshold(blur, 255,
                                  cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                  cv2.THRESH_BINARY_INV,
                                  31, 15)
    kernel_close = np.ones((2, 2), np.uint8)
    closed = cv2.morphologyEx(adapt, cv2.MORPH_CLOSE, kernel_close, iterations=1)
    kernel_dilate = np.ones((2, 2), np.uint8)
    dilated = cv2.dilate(closed, kernel_dilate, iterations=1)
    return dilated

def deskew_and_clean(image_bgr):
    try:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 50, 200)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        plate_candidate = None
        max_area = 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 1000:  # Ajusta según el tamaño esperado de la placa
                peri = cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
                if len(approx) == 4 and area > max_area:
                    max_area = area
                    plate_candidate = approx
        if plate_candidate is not None:
            pts = plate_candidate.reshape(4, 2)
            rect = order_points(pts)
            W, H = 300, 100
            dst = np.array([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]], dtype="float32")
            M = cv2.getPerspectiveTransform(rect, dst)
            warp = cv2.warpPerspective(image_bgr, M, (W, H))
            return warp
        else:
            return image_bgr
    except Exception as e:
        print(f"[WARN] deskew_and_clean: {e}")
        return image_bgr

def order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect

##############################################
# Hilo de procesamiento de frames
##############################################
def process_frames():
    global frame_original, frame_processed
    cap = cv2.VideoCapture(rtsp_url)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if not cap.isOpened():
        print("[ERROR] No se pudo abrir la cámara RTSP.")
        return
    fallback_count = 0
    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            print("[WARN] No se obtuvo frame. Reintentando en 5s...")
            time.sleep(5)
            cap.release()
            cap = cv2.VideoCapture(rtsp_url)
            continue

        frame_original = frame.copy()
        frame_processed = frame.copy()
        cv2.rectangle(frame_processed, (roi_x, roi_y),
                      (roi_x + roi_w, roi_y + roi_h),
                      (0, 255, 0), 2)
        hsv = cv2.cvtColor(frame_processed, cv2.COLOR_BGR2HSV)
        lower_yellow = np.array([20, 100, 100])
        upper_yellow = np.array([30, 255, 255])
        mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)
        lower_white = np.array([0, 0, 200])
        upper_white = np.array([180, 30, 255])
        mask_white = cv2.inRange(hsv, lower_white, upper_white)
        mask_combined = cv2.bitwise_or(mask_yellow, mask_white)
        roi_mask = mask_combined[roi_y:roi_y+roi_h, roi_x:roi_x+roi_w]

        if cv2.countNonZero(roi_mask) > 500:
            while not ocr_queue.empty():
                try:
                    ocr_queue.get_nowait()
                except Exception:
                    break
            ocr_queue.put(frame[roi_y:roi_y+roi_h, roi_x:roi_x+roi_w])
            fallback_count = 0
        else:
            fallback_count += 1
            if fallback_count >= 30:
                fallback_count = 0
                while not ocr_queue.empty():
                    try:
                        ocr_queue.get_nowait()
                    except Exception:
                        break
                ocr_queue.put(frame[roi_y:roi_y+roi_h, roi_x:roi_x+roi_w])
        time.sleep(0.01)

##############################################
# Hilo de OCR (sin redundancia extra)
##############################################
def process_ocr():
    global number_samples, letter_samples, confirmed_plate, pending_plate, pending_count, last_confirmed_time
    global cooldown_seconds
    while True:
        roi_image = ocr_queue.get()
        if roi_image is None:
            break
        try:
            # Si la misma placa se confirmó recientemente, saltar procesamiento
            if confirmed_plate and (time.time() - last_confirmed_time) < cooldown_seconds:
                continue

            plate_rectified = deskew_and_clean(roi_image)
            preprocessed = advanced_preprocessing(plate_rectified)
            config_tess = "--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            detected_text = pytesseract.image_to_string(preprocessed, config=config_tess).strip()
            filtered_text = "".join(ch for ch in detected_text if ch.isalnum()).upper()

            letters = "".join(c for c in filtered_text if c.isalpha())
            numbers = "".join(c for c in filtered_text if c.isdigit())

            if len(numbers) == 3:
                number_samples.append(numbers)
                if len(number_samples) > sample_limit:
                    number_samples.pop(0)
            if len(letters) == 3:
                letter_samples.append(letters)
                if len(letter_samples) > sample_limit:
                    letter_samples.pop(0)

            if len(number_samples) >= sample_limit and len(letter_samples) >= sample_limit:
                mc_numbers = Counter(number_samples).most_common(1)
                mc_letters = Counter(letter_samples).most_common(1)
                if mc_numbers and mc_letters:
                    new_plate = f"{mc_letters[0][0]} {mc_numbers[0][0]}"
                    if new_plate == confirmed_plate:
                        continue
                    if new_plate == pending_plate:
                        pending_count += 1
                        if pending_count >= confirmation_threshold:
                            confirmed_plate = new_plate
                            last_confirmed_time = time.time()
                            print(f"[INFO] Placa detectada: {confirmed_plate}")
                            threading.Thread(target=send_plate_to_server, args=(confirmed_plate,), daemon=True).start()
                            pending_count = 0
                    else:
                        pending_plate = new_plate
                        pending_count = 1

        except Exception as e:
            print(f"[ERROR] process_ocr: {e}")

##############################################
# Rutas Flask para streaming
##############################################
@app.route("/video_feed")
def video_feed():
    def gen():
        global frame_original
        while True:
            if frame_original is not None:
                ret, buf = cv2.imencode(".jpg", frame_original)
                if ret:
                    yield (b"--frame\r\n"
                           b"Content-Type: image/jpeg\r\n\r\n" +
                           buf.tobytes() +
                           b"\r\n")
            else:
                time.sleep(0.01)
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/processed_feed")
def processed_feed():
    def gen():
        global frame_processed
        while True:
            if frame_processed is not None:
                ret, buf = cv2.imencode(".jpg", frame_processed)
                if ret:
                    yield (b"--frame\r\n"
                           b"Content-Type: image/jpeg\r\n\r\n" +
                           buf.tobytes() +
                           b"\r\n")
            else:
                time.sleep(0.01)
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

##############################################
# MAIN: iniciar hilos y Flask
##############################################
if __name__ == "__main__":
    # Inicializar cooldown
    last_confirmed_time = 0
    cooldown_seconds = 5

    threading.Thread(target=process_ocr, daemon=True).start()
    threading.Thread(target=process_frames, daemon=True).start()
    app.run(host="0.0.0.0", port=5001, debug=False)

