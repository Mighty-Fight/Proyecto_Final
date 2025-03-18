import cv2
import numpy as np
import pytesseract
import threading
import queue
import time
import base64
from collections import Counter
# Descomentar las importaciones para la nube
from flask import Flask, Response, jsonify
import requests

print("✅ Script camnew.py iniciado...")



# ===============================
# Configuración Tesseract
# ===============================
#pytesseract.pytesseract.tesseract_cmd = r"/usr/local/bin/tesseract"

# Comentado el path local de Tesseract para funcionamiento local
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ===============================
# Parámetros de la cámara y ROI
# ===============================
rtsp_url = "rtsp://admin:abcd1234..@186.119.52.250:554/Streaming/Channels/101"
width, height = 1280, 720
roi_x, roi_y, roi_w, roi_h = 400, 200, 500, 200

print("📷 Conectando a la cámara en:", rtsp_url)

# ===============================
# Cola y variables para OCR
# Se usa una cola con maxsize=1 para procesar siempre el último frame
# ===============================
ocr_queue = queue.Queue(maxsize=1)
number_samples = []
letter_samples = []
candidate_history = []  
sample_limit = 9
WINDOW_SIZE = 9
OVERRIDE_THRESHOLD = 9  # Mínimo número de ocurrencias en la ventana para confirmar un candidato

confirmed_plate = ""  # Placa confirmada final
pending_plate = ""    # Placa pendiente
pending_count = 0

# AJUSTE: Se cambia el threshold a 3 para requerir 3 lecturas iguales
confirmation_threshold = 3

# Variables para cooldown
last_confirmed_time = 0
cooldown_seconds = 5  # Tiempo de inactividad para ignorar la misma placa

# Variable global para mostrar la imagen original
frame_original = None
frame_processed = None
isHighResCaptured = False

##############################################
# Inicializar la app Flask para la nube
##############################################
app = Flask(__name__)

##############################################
# Funciones de preprocesamiento (originales)
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

def unsharp_mask(image, kernel_size=(5,5), sigma=1.0, amount=1.0, threshold=0):
    blurred = cv2.GaussianBlur(image, kernel_size, sigma)
    sharpened = float(amount + 1)*image - float(amount)*blurred
    sharpened = np.clip(sharpened, 0, 255).astype(np.uint8)
    if threshold > 0:
        low_contrast_mask = np.abs(image - blurred) < threshold
        np.copyto(sharpened, image, where=low_contrast_mask)
    return sharpened

def advanced_preprocessing(image_bgr):
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    
    # CLAHE para aumentar contraste local
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    clahe_img = clahe.apply(gray)

    # Unsharp mask para realzar bordes
    sharpened = unsharp_mask(clahe_img, kernel_size=(5,5), sigma=1.0, amount=1.5, threshold=0)

    # Umbral adaptativo
    blur = cv2.GaussianBlur(sharpened, (3,3), 0)
    adapt = cv2.adaptiveThreshold(blur, 255,
                                  cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                  cv2.THRESH_BINARY_INV,
                                  31, 15)

    # Pequeña dilatación y cierre morfológico
    kernel_close = np.ones((2,2), np.uint8)
    closed = cv2.morphologyEx(adapt, cv2.MORPH_CLOSE, kernel_close, iterations=1)
    kernel_dilate = np.ones((2,2), np.uint8)
    dilated = cv2.dilate(closed, kernel_dilate, iterations=1)

    return dilated
##############################################
# Hilo de procesamiento de frames (original)
##############################################
def process_frames():
    global frame_original, frame_processed, isHighResCaptured
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

        # Delimitar el área de análisis con un cuadro verde (ROI)
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

        # MISMA CONDICIÓN: si hay suficiente actividad en ROI
        if cv2.countNonZero(roi_mask) > 500:
            # Si todavía NO hemos capturado alta resolución, lo hacemos UNA vez
            if not isHighResCaptured:
                print("Cambio a alta resolución para OCR preciso (una sola vez).")
                # Cambiar a 1920x1080
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1080)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                time.sleep(0.1)  # Espera un instante

                ret2, highResFrame = cap.read()
                if ret2 and highResFrame is not None:
                    # Limpiar la cola
                    while not ocr_queue.empty():
                        try:
                            ocr_queue.get_nowait()
                        except Exception:
                            break
                    # Poner en la cola la ROI del frame de alta resolución
                    roi_high = highResFrame[roi_y:roi_y+roi_h, roi_x:roi_x+roi_w]
                    ocr_queue.put(roi_high)
                    print("Frame alta resolución agregado. ROI shape:", roi_high.shape)

                    # Volver a la resolución normal
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                    isHighResCaptured = True
                else:
                    print("Error capturando frame de alta resolución.")
            else:
                # Si ya capturamos una vez en alta resolución, sigue la lógica original
                while not ocr_queue.empty():
                    try:
                        ocr_queue.get_nowait()
                    except Exception:
                        break
                ocr_queue.put(frame[roi_y:roi_y+roi_h, roi_x:roi_x+roi_w])
            fallback_count = 0

        else:
            # Lógica original de fallback
            fallback_count += 1
            if fallback_count >= 30:
                fallback_count = 0
                # Reiniciamos isHighResCaptured para permitir nueva captura
                isHighResCaptured = False

                while not ocr_queue.empty():
                    try:
                        ocr_queue.get_nowait()
                    except Exception:
                        break
                ocr_queue.put(frame[roi_y:roi_y+roi_h, roi_x:roi_x+roi_w])

        time.sleep(0.01)

##############################################
# FUNCIÓN NUEVA: Para medir diferencia de caracteres entre dos placas
##############################################
def plate_diff(plate1, plate2):
    """
    Retorna el número de caracteres diferentes entre dos cadenas de igual longitud.
    Si difieren en longitud, asumimos diferencia total (por ejemplo, 6).
    """
    if len(plate1) != len(plate2):
        return max(len(plate1), len(plate2))
    return sum(a != b for a, b in zip(plate1, plate2))

##############################################
# Hilo de OCR (original) con la nueva lógica
##############################################
def auto_crop_plate(bin_img, gap_threshold=0.1, min_gap_rows=20):
    """
    Recorta la parte inferior de una imagen binaria (bin_img) si detecta
    una zona con pocas filas activas (usada para descartar textos extra, 
    como "BARRANQUILLA").
    
    - gap_threshold: porcentaje de píxeles (de la anchura) para considerar
      que una fila está "vacía".
    - min_gap_rows: número mínimo de filas consecutivas que deben estar "vacías"
      para establecer la línea de corte.
      
    Retorna la subimagen (desde la parte superior hasta la línea de corte).
    """
    h, w = bin_img.shape
    consecutive_gap = 0
    cut_line = h  # Por defecto, sin recorte

    # Recorremos desde la última fila hacia la primera
    for row in range(h - 1, -1, -1):
        whites = cv2.countNonZero(bin_img[row:row+1, :])
        if whites < gap_threshold * w:
            consecutive_gap += 1
        else:
            consecutive_gap = 0
        if consecutive_gap >= min_gap_rows:
            cut_line = row + min_gap_rows  # Cortamos un poco más arriba
            break

    return bin_img[:cut_line, :]

def process_ocr():
    global number_samples, letter_samples, confirmed_plate, candidate_history, last_confirmed_time
    global cooldown_seconds, sample_limit, WINDOW_SIZE, OVERRIDE_THRESHOLD

    while True:
        roi_image = ocr_queue.get()
        if roi_image is None:
            break
        try:
            # Si ya hay una placa confirmada y aún no pasó el cooldown, se ignoran nuevas lecturas
            if confirmed_plate and (time.time() - last_confirmed_time) < cooldown_seconds:
                continue

            plate_rectified = deskew_and_clean(roi_image)
            preprocessed = advanced_preprocessing(plate_rectified)
            
            # Recortar automáticamente la parte inferior para descartar texto extra
            cropped = auto_crop_plate(preprocessed, gap_threshold=0.1, min_gap_rows=20)
            
            config_tess = "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            detected_text = pytesseract.image_to_string(cropped, config=config_tess).strip()
            filtered_text = "".join(ch for ch in detected_text if ch.isalnum()).upper()
            
            print("Detected text:", detected_text)
            print("Filtered text:", filtered_text)
            
            # Separar letras y números
            letters = "".join(c for c in filtered_text if c.isalpha())
            numbers = "".join(c for c in filtered_text if c.isdigit())
            
            # Si se detectan más de 3 letras o dígitos, quedarse solo con los 3 primeros
            if len(letters) > 3:
                print(f"[PostCorrection] Ajustando letras: {letters} => {letters[:3]}")
                letters = letters[:3]
            if len(numbers) > 3:
                print(f"[PostCorrection] Ajustando números: {numbers} => {numbers[:3]}")
                numbers = numbers[:3]
            
            # Considerar solo lecturas con exactamente 3 letras y 3 números
            if len(letters) == 3 and len(numbers) == 3:
                new_plate = f"{letters} {numbers}"
                print("Nuevo candidato:", new_plate)
                
                # Acumular el candidato en la ventana
                candidate_history.append(new_plate)
            
            # Si se han acumulado suficientes muestras en la ventana
            if len(candidate_history) >= WINDOW_SIZE:
                mode_plate, count = Counter(candidate_history).most_common(1)[0]
                print(f"[STABILITY] Ventana: {candidate_history}")
                print(f"[STABILITY] Mode: {mode_plate} ({count}/{WINDOW_SIZE})")
                # Si el candidato más frecuente se repite lo suficiente y es diferente al confirmado
                if count >= OVERRIDE_THRESHOLD and mode_plate != confirmed_plate:
                    confirmed_plate = mode_plate
                    last_confirmed_time = time.time()
                    print(f"[INFO] Placa confirmada: {confirmed_plate}")
                    
                    # Codificar la imagen recortada en base64 para enviarla al servidor
                    ret_jpg, buf = cv2.imencode('.jpg', cropped)
                    if ret_jpg:
                        frame_b64 = base64.b64encode(buf).decode('utf-8')
                    else:
                        frame_b64 = None
                    payload = {"placa": confirmed_plate}
                    if frame_b64:
                        payload["frame"] = frame_b64
                    try:
                        requests.post("http://44.211.67.168/update", json=payload)
                    except Exception as e:
                        print(f"Error enviando la placa al servidor Node: {e}")
                # Reiniciar la ventana para la siguiente toma
                candidate_history = []
        except Exception as e:
            print(f"[ERROR] process_ocr: {e}")
#################################################################
# Funcionalidades adicionales para detección confiable de placas
#################################################################

def preprocess_plate_roi(plate_roi):
    if plate_roi is None:
        return None
    # Aquí se podría implementar el preprocesamiento avanzado (mediana, CLAHE, umbral adaptativo, etc.)
    return plate_roi  # Placeholder, se mantiene el código original

def extract_plate_roi(image):
    return None       # Placeholder

def ocr_plate(plate_image):
    return ""         # Placeholder

tracker = None
bbox = None

def process_improved_plate():
    while True:
        if frame_original is None:
            time.sleep(0.01)
            continue
        # Placeholder para pipeline mejorado con tracking
        time.sleep(0.5)

def print_plate_console():
    global confirmed_plate
    last_plate = ""
    while True:
        if confirmed_plate and confirmed_plate != last_plate:
            print(f"[FINAL] Placa detectada: {confirmed_plate}")
            last_plate = confirmed_plate
        time.sleep(0.5)

#################################################################
# Endpoints para streaming en la nube (descomentados)
#################################################################
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

@app.route("/latest_plate", methods=["GET"])
def latest_plate():
    global confirmed_plate, last_confirmed_time
    if confirmed_plate and last_confirmed_time:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_confirmed_time))
    else:
        timestamp = "--"
    return jsonify({
        "plate": confirmed_plate if confirmed_plate else "No se ha detectado ninguna placa aún",
        "timestamp": timestamp
    })

##############################################
# MAIN: iniciar hilos y funcionamiento en la nube
##############################################
if __name__ == "__main__":
    # Inicializar cooldown
    last_confirmed_time = 0

    # Iniciar hilos para procesamiento original
    threading.Thread(target=process_ocr, daemon=True).start()
    threading.Thread(target=process_frames, daemon=True).start()
    
    # Iniciar nuevo hilo con el pipeline mejorado (con tracking) para la ROI
    threading.Thread(target=process_improved_plate, daemon=True).start()
    
    # Iniciar hilo adicional para imprimir la placa detectada en consola (del pipeline original)
    threading.Thread(target=print_plate_console, daemon=True).start()

    # Comentado: funcionamiento local (ventana emergente)
    """
    while True:
        if frame_original is not None:
            display_frame = frame_original.copy()
            cv2.rectangle(display_frame, (roi_x, roi_y), (roi_x+roi_w, roi_y+roi_h), (0,255,0), 2)
            cv2.imshow("Camara en Vivo", display_frame)
            cv2.imshow("Área de Análisis", display_frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cv2.destroyAllWindows()
    """
    
    # Descomentar: ejecutar la app Flask para funcionamiento en la nube
    app.run(host="0.0.0.0", port=5001, debug=False)

if __name__ == "__main__":
    # Inicializar cooldown
    last_confirmed_time = 0

    # Iniciar hilos para procesamiento de OCR y detección de placas
    threading.Thread(target=process_ocr, daemon=True).start()
    threading.Thread(target=process_frames, daemon=True).start()

    # 📷 Mostrar la transmisión en una ventana de OpenCV
    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        print("❌ No se pudo abrir la cámara RTSP.")
    else:
        print("✅ Transmisión en vivo iniciada... Presiona 'Q' para salir.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("⚠️ No se pudo obtener frame. Reintentando...")
            time.sleep(1)
            continue

        # Dibuja un rectángulo para marcar la ROI (donde se detecta la placa)
        cv2.rectangle(frame, (roi_x, roi_y), (roi_x + roi_w, roi_y + roi_h), (0, 255, 0), 2)

        # Muestra la imagen en la ventana
        cv2.imshow("Transmisión en Vivo", frame)

        # Salir con la tecla "Q"
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    
    