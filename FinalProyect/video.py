import cv2
import pytesseract
import numpy as np
import re
from collections import deque
import requests  # Para enviar solicitudes HTTP
from base_db import conectar_db, verificar_placa, cerrar_conexion  # Importamos las funciones de base_db

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Función para ajustar brillo, contraste y aplicar un filtro de nitidez
def adjust_brightness_contrast_sharpness(image, brightness=0, contrast=30):
    if brightness != 0:
        if brightness > 0:
            shadow = brightness
            highlight = 255
        else:
            shadow = 0
            highlight = 255 + brightness
        alpha_b = (highlight - shadow) / 255
        gamma_b = shadow
        image = cv2.addWeighted(image, alpha_b, image, 0, gamma_b)

    if contrast != 0:
        f = 131 * (contrast + 127) / (127 * (131 - contrast))
        alpha_c = f
        gamma_c = 127 * (1 - f)
        image = cv2.addWeighted(image, alpha_c, image, 0, gamma_c)

    return image

# Filtro de nitidez más suave
def apply_sharpness(image):
    kernel = np.array([[0, -0.52, 0], [-0.52, 5, -0.52], [0, -0.52, 0]])  # Filtro de nitidez
    image = cv2.filter2D(image, -1, kernel)
    return image

# Para almacenar lecturas consecutivas
lecturas_consecutivas = deque(maxlen=5)  # Almacena las últimas 5 lecturas de placas

roi_x, roi_y = 680, 550  # Coordenadas del ROI (Región de Interés)
roi_w, roi_h = 600, 400  # Ancho y alto del ROI

cap = cv2.VideoCapture('prueba_video1.mp4')

if not cap.isOpened():
    print("Error al abrir el archivo de video.")
    exit()

# Conectarse a la base de datos
conn = conectar_db()

# Nueva función para enviar el estado de la placa al servidor web
def enviar_estado_placa(estado):
    try:
        url = 'http://localhost:3000'  # La dirección del servidor web
        requests.post(f'{url}/update', json={'estado': estado})
    except Exception as e:
        print(f'Error al enviar datos al servidor: {e}')

while cap.isOpened():
    ret, frame = cap.read()

    if not ret:
        print("Fin del video o error al capturar el fotograma.")
        break

    # Ajustar brillo y contraste de toda la imagen
    frame = adjust_brightness_contrast_sharpness(frame, brightness=-20, contrast=40)

    # Extraer la región de interés (ROI)
    roi_frame = frame[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]

    # Aplicar filtro de nitidez solo dentro del ROI
    roi_frame = apply_sharpness(roi_frame)

    # Convertir a espacio de color HSV
    hsv = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)

    lower_yellow = np.array([22, 103, 105])
    upper_yellow = np.array([35, 255, 255])

    mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    placa_detectada = False

    if len(contours) > 0:
        for cnt in contours:
            area = cv2.contourArea(cnt)

            if area > 500:
                epsilon = 0.03 * cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, epsilon, True)

                if len(approx) == 4:
                    placa_detectada = True
                    rx, ry, rw, rh = cv2.boundingRect(cnt)
                    plate_image = roi_frame[ry:ry+rh, rx:rx+rw]

                    gray = cv2.cvtColor(plate_image, cv2.COLOR_BGR2GRAY)
                    gray = cv2.GaussianBlur(gray, (3, 3), 0)
                    gray = cv2.equalizeHist(gray)

                    _, binary = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY)

                    kernel = np.ones((2, 2), np.uint8)
                    binary = cv2.dilate(binary, kernel, iterations=1)
                    binary = cv2.erode(binary, kernel, iterations=1)

                    plate_image = cv2.resize(plate_image, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

                    text = pytesseract.image_to_string(binary, config='--psm 7')
                    text = re.sub(r'[^A-Z0-9]', '', text)

                    if len(text) == 6:
                        # Añadir la lectura a la lista de lecturas consecutivas
                        lecturas_consecutivas.append(text)

                        # Confirmar la lectura si las lecturas coinciden en un porcentaje
                        if len(lecturas_consecutivas) == 5:
                            coincidencias = [lecturas_consecutivas.count(x) for x in lecturas_consecutivas]
                            mayor_frecuencia = max(coincidencias)
                            porcentaje_coincidencia = (mayor_frecuencia / 5) * 100

                            if porcentaje_coincidencia >= 80:  # Si el 80% o más son iguales
                                placa_final = max(set(lecturas_consecutivas), key=lecturas_consecutivas.count)
                                placa_final = placa_final[:3] + '-' + placa_final[3:]

                                # Verificar la placa en la base de datos
                                existe = verificar_placa(placa_final, conn)

                                if existe:
                                    mensaje = f"Placa {placa_final} está registrada en la base de datos."
                                else:
                                    mensaje = f"Placa {placa_final} no está registrada en la base de datos."

                                print(mensaje)
                                enviar_estado_placa(mensaje)  # Enviar el mensaje al servidor web

                                cv2.rectangle(roi_frame, (rx, ry), (rx + rw, ry + rh), (0, 255, 0), 2)
                                cv2.putText(roi_frame, placa_final.strip(), (rx, ry - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                                cv2.imshow("Detección de Placa", roi_frame)

                                cv2.waitKey(2000)

    resized_frame = cv2.resize(roi_frame, (640, 360))
    resized_mask = cv2.resize(mask, (640, 360))

    cv2.imshow("Detección de Placa", resized_frame)
    cv2.imshow("Máscara Amarillo", resized_mask)
    cv2.rectangle(frame, (roi_x, roi_y), (roi_x + roi_w, roi_y + roi_h), (0, 255, 0), 2)
    cv2.imshow("Video Completo con ROI", cv2.resize(frame, (640, 360)))

    if cv2.waitKey(25) & 0xFF == ord('q'):
        break

# Cerrar la conexión a la base de datos
cerrar_conexion(conn)

cap.release()
cv2.destroyAllWindows()