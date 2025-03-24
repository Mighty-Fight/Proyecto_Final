import cv2
import numpy as np
import pytesseract
import pytz
import time
from datetime import datetime
from collections import Counter

# === CONFIG ===
rtsp_url = "rtsp://admin:abcd1234..@181.236.141.192:554/Streaming/Channels/101"
roi_coords = (180, 120, 300, 200)

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# === ESTADO ===
last_plate = None
last_detection_time = 0
last_seen_time = 0
PLATE_DISAPPEAR_TIMEOUT = 60  # segundos

# === FUNCIONES ===

def timestamp_bogota():
    bogota = pytz.timezone("America/Bogota")
    now = datetime.now(bogota)
    return now.strftime("%Y-%m-%d_%H-%M-%S")

def generar_nombre_archivo(placa):
    return f"{placa}_{timestamp_bogota()}.png"

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
    global last_plate, last_detection_time, last_seen_time

    print("🔍 Procesando frame para OCR...")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 200)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    plate_candidate = max(
        (cnt for cnt in contours if cv2.contourArea(cnt) > 1000),
        default=None,
        key=cv2.contourArea
    )
    if plate_candidate is None:
        print("❗ No se encontró ningún contorno válido.")
        return

    approx = cv2.approxPolyDP(plate_candidate, 0.02 * cv2.arcLength(plate_candidate, True), True)

    # Bounding box si no tiene 4 lados
    if len(approx) != 4:
        print(f"⚠️ Contorno con {len(approx)} lados → usando bounding box")
        x, y, w, h = cv2.boundingRect(plate_candidate)
        rect = order_points(np.array([
            [x, y],
            [x+w, y],
            [x+w, y+h],
            [x, y+h]
        ], dtype="float32"))
    else:
        rect = order_points(approx.reshape(4, 2))

    W, H = 300, 100
    M = cv2.getPerspectiveTransform(rect, np.array([[0, 0], [W-1, 0], [W-1, H-1], [0, H-1]], dtype="float32"))
    warped = cv2.warpPerspective(image, M, (W, H))
    cropped = warped[:int(H*0.8), :]

    scaled = cv2.resize(cropped, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    config = "--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    # OCR múltiple
    lecturas = []
    for i in range(9):
        ocr_raw = pytesseract.image_to_string(scaled, config=config).strip()
        lectura = "".join(c for c in ocr_raw if c.isalnum()).upper()
        if lectura:
            lecturas.append(lectura)

    if not lecturas:
        print("❗ OCR falló en todas las pasadas.")
        return

    # Elegir lectura más repetida
    filtrado = Counter(lecturas).most_common(1)[0][0]

    print("📷 OCR múltiples lecturas:", lecturas)
    print(f"🧠 Lectura más frecuente entre 9 intentos: {filtrado}")

    letras = "".join(c for c in filtrado if c.isalpha())[:3]
    numeros = "".join(c for c in filtrado if c.isdigit())[:3]

    if len(letras) == 3 and len(numeros) == 3:
        placa = f"{letras}{numeros}"
        current_time = time.time()

        if placa == last_plate:
            tiempo_sin_ver = current_time - last_seen_time
            if tiempo_sin_ver < PLATE_DISAPPEAR_TIMEOUT:
                print(f"⏩ Placa aún presente: {placa} | Ignorada (última vista hace {tiempo_sin_ver:.2f}s)")
                last_seen_time = current_time
                return
            else:
                print(f"🔁 Placa {placa} estuvo ausente {tiempo_sin_ver:.2f}s → se considera nueva")

        last_plate = placa
        last_detection_time = current_time
        last_seen_time = current_time

        nombre_archivo = generar_nombre_archivo(placa)
        cv2.imwrite(f"D:/Proyecto_Final/Proyecto_Final/FinalProyect/scripts/{nombre_archivo}", image)
        print(f"✅ Placa detectada: {placa}")
        print(f"💾 Imagen guardada como: {nombre_archivo}")
    else:
        print("❗ No se pudo detectar una placa válida.")

# === STREAM LOOP ===
cap = cv2.VideoCapture(rtsp_url)
if not cap.isOpened():
    print("❌ No se pudo conectar al stream.")
    exit()

print("📡 Stream conectado. Procesando en tiempo real...")

while True:
    ret, frame = cap.read()
    if not ret:
        print("⚠️ Frame no disponible.")
        continue

    x, y, w, h = roi_coords
    roi = frame[y:y+h, x:x+w]
    cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 255, 0), 2)

    if detectar_por_color(roi) or detectar_por_forma(roi):
        print("🚨 Posible placa detectada...")
        detectar_placa_desde_imagen(frame)

    cv2.imshow("🎥 Stream en vivo", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("🛑 Salida manual.")
        break

cap.release()
cv2.destroyAllWindows()
