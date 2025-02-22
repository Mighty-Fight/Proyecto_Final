import ffmpeg
import numpy as np
import cv2
import pytesseract
import re

# Configuración de Tesseract para OCR
pytesseract.pytesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# URL RTSP de la cámara IP
rtsp_url = "rtsp://admin:abcd1234..@181.236.141.139:554/Streaming/Channels/101"

# Configuración de tamaño de frame
width, height = 1280, 720

# Dimensiones del ROI (Región de Interés)
roi_w, roi_h = 600, 400

# Calcular las coordenadas para centrar el ROI en el frame
roi_x = (width - roi_w) // 2
roi_y = (height - roi_h) // 2

def start_ffmpeg_process():
    """Inicia el proceso de ffmpeg para la transmisión RTSP."""
    return (
        ffmpeg
        .input(rtsp_url)
        .output('pipe:', format='rawvideo', pix_fmt='bgr24')
        .run_async(pipe_stdout=True)  # Permitimos que stderr vaya a la consola para evitar bloqueos
    )

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

# Filtro de nitidez
def apply_sharpness(image):
    kernel = np.array([[0, -0.52, 0], [-0.52, 5, -0.52], [0, -0.52, 0]])
    image = cv2.filter2D(image, -1, kernel)
    return image

# Inicia el proceso de ffmpeg
process = start_ffmpeg_process()

while True:
    try:
        # Leer los bytes necesarios para un frame de video
        in_bytes = process.stdout.read(width * height * 3)
        if not in_bytes:
            raise ValueError("No se pudo obtener el frame.")
        
        # Convertir los bytes a una imagen en formato numpy
        frame = np.frombuffer(in_bytes, np.uint8).reshape([height, width, 3])

        # Ajustar brillo y contraste de toda la imagen
        frame = adjust_brightness_contrast_sharpness(frame, brightness=-20, contrast=40)

        # Extraer la región de interés (ROI) centrada
        roi_frame = frame[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]

        # Aplicar filtro de nitidez solo dentro del ROI
        roi_frame = apply_sharpness(roi_frame)

        # Convertir a espacio de color HSV y crear una máscara para el amarillo
        hsv = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)
        lower_yellow = np.array([22, 20, 255])
        upper_yellow = np.array([60, 255, 255])
        mask = cv2.inRange(hsv, lower_yellow, upper_yellow)

        # Aplicar la máscara para visualizar la placa en blanco y negro
        filtered_frame = cv2.bitwise_and(roi_frame, roi_frame, mask=mask)
        gray = cv2.cvtColor(filtered_frame, cv2.COLOR_BGR2GRAY)
        _, binary_mask = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY)

        # Detectar contornos en la máscara
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if len(contours) > 0:
            for cnt in contours:
                area = cv2.contourArea(cnt)

                if area > 500:
                    epsilon = 0.03 * cv2.arcLength(cnt, True)
                    approx = cv2.approxPolyDP(cnt, epsilon, True)

                    if len(approx) == 4:
                        rx, ry, rw, rh = cv2.boundingRect(cnt)
                        plate_image = roi_frame[ry:ry + rh, rx:rx + rw].copy()  # Tomar una copia de la imagen de la placa

                        # Procesar la imagen de la placa en blanco y negro para OCR
                        gray = cv2.cvtColor(plate_image, cv2.COLOR_BGR2GRAY)
                        gray = cv2.GaussianBlur(gray, (3, 3), 0)
                        gray = cv2.equalizeHist(gray)
                        _, binary_plate = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY)
                        kernel = np.ones((2, 2), np.uint8)
                        binary_plate = cv2.dilate(binary_plate, kernel, iterations=1)
                        binary_plate = cv2.erode(binary_plate, kernel, iterations=1)
                        plate_image_resized = cv2.resize(binary_plate, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

                        # OCR para extraer texto de la placa
                        text = pytesseract.image_to_string(plate_image_resized, config='--psm 7')
                        text = re.sub(r'[^A-Z0-9]', '', text)

                        # Imprimir el texto detectado directamente
                        if text:
                            print("Texto detectado:", text)

        # Mostrar la máscara de la placa en blanco y negro
        resized_mask = cv2.resize(binary_mask, (640, 360))
        cv2.imshow("Máscara Amarillo", resized_mask)

        # Mostrar el video completo con el área del ROI resaltada
        cv2.rectangle(frame, (roi_x, roi_y), (roi_x + roi_w, roi_y + roi_h), (0, 255, 0), 2)
        cv2.imshow("Video Completo con ROI", frame)
        cv2.imshow("Detección de Placa", roi_frame)

        # Salir al presionar 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    except Exception as e:
        print(f"Error: {e}. Reintentando en 5 segundos...")
        process.terminate()
        time.sleep(5)
        process = start_ffmpeg_process()

# Terminar proceso y cerrar ventanas
process.terminate()
cv2.destroyAllWindows()







































