import cv2
import numpy as np
import time

# === CONFIGURACIÓN ===
rtsp_url = "rtsp://admin:abcd1234..@181.236.149.17:554/Streaming/Channels/101"
save_path = "D:/Proyecto_Final/Proyecto_Final/FinalProyect/scripts/imagen_papi2.png"
roi_coords = (180, 120, 300, 200)  # x, y, w, h

# === FUNCIONES AUXILIARES ===
def detectar_por_color(roi):
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    blanco = cv2.inRange(hsv, (0, 0, 170), (180, 60, 255))
    amarillo = cv2.inRange(hsv, (15, 50, 150), (35, 255, 255))
    total = roi.shape[0] * roi.shape[1]
    blanco_ratio = cv2.countNonZero(blanco) / total
    amarillo_ratio = cv2.countNonZero(amarillo) / total
    return blanco_ratio > 0.2 or amarillo_ratio > 0.2

def detectar_por_forma(roi):
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 200)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 800:
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            if 4 <= len(approx) <= 6:
                return True
    return False

# === CAPTURA EN VIVO ===
cap = cv2.VideoCapture(rtsp_url)

if not cap.isOpened():
    print("❌ No se pudo conectar al stream RTSP.")
    exit()

print("📡 Conectado al stream. Buscando posible placa...")

while True:
    ret, frame = cap.read()
    if not ret:
        print("⚠️ No se pudo leer el frame.")
        break

    # No escales el frame. Usa tal cual lo entrega la cámara.

    x, y, w, h = roi_coords
    roi = frame[y:y+h, x:x+w]
    cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 255, 0), 2)

    if detectar_por_color(roi):
        print("🟡 Detected color de placa (blanco o amarillo)")
        cv2.imwrite(save_path, frame)
        print(f"📸 Imagen completa guardada como imagen.png")
        break

    if detectar_por_forma(roi):
        print("🟩 Detectada forma rectangular en ROI")
        cv2.imwrite(save_path, frame)
        print(f"📸 Imagen completa guardada como imagen_papi2.png")
        break

    cv2.imshow("🎥 Stream RTSP", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("❌ Cancelado por el usuario.")
        break

cap.release()
cv2.destroyAllWindows()
