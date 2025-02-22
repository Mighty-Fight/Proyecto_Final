import ffmpeg
import numpy as np
import cv2
import pytesseract
import threading
import queue
from collections import Counter

# Configuración de Tesseract-OCR
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# URL RTSP de la cámara IP
rtsp_url = "rtsp://admin:abcd1234..@181.236.158.144:554/Streaming/Channels/101"

# Ruta completa al archivo ejecutable de FFmpeg
ffmpeg_path = r"C:\ffmpeg\ffmpeg.exe"

# Configura el tamaño de la ventana y la resolución
width, height = 1280, 720
roi_x, roi_y, roi_w, roi_h = 400, 200, 500, 200  # Ajusta para incluir toda la placa

# Variables para manejar el procesamiento
ocr_queue = queue.Queue()
number_samples = []  # Almacena los últimos números detectados
letter_samples = []  # Almacena las últimas letras detectadas
sample_limit = 3  # Número mínimo de muestras antes de tomar una decisión

# Confirmación de letras y números
confirmed_plate = ""  # Placa confirmada (formato completo)
pending_plate = ""  # Placa en proceso de confirmación
pending_count = 0  # Contador para confirmar una nueva placa
confirmation_threshold = 2  # Número de detecciones consecutivas necesarias para confirmar

def start_ffmpeg_process():
    """Inicia el proceso de ffmpeg para la transmisión RTSP."""
    try:
        return (
            ffmpeg
            .input(rtsp_url)
            .output('pipe:', format='rawvideo', pix_fmt='bgr24')
            .run_async(pipe_stdout=True, cmd=ffmpeg_path)
        )
    except FileNotFoundError as e:
        print(f"Error: No se encontró FFmpeg en la ruta especificada. Verifica la instalación y el PATH: {e}")
        raise
    except Exception as e:
        print(f"Error al iniciar FFmpeg: {e}")
        raise

def process_ocr():
    """Hilo separado para procesar OCR."""
    global number_samples, letter_samples, confirmed_plate, pending_plate, pending_count

    while True:
        # Esperar un ROI en la cola
        roi_image = ocr_queue.get()
        if roi_image is None:
            break

        try:
            # Preprocesar la imagen para OCR
            gray = cv2.cvtColor(roi_image, cv2.COLOR_BGR2GRAY)

            # Aplicar umbral binario directamente para mejorar velocidad
            _, binary = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY)

            # Usar Tesseract para extraer texto
            detected_text = pytesseract.image_to_string(binary, config='--psm 8').strip()

            # Filtrar texto para números y letras
            filtered_text = ''.join(char for char in detected_text if char.isalnum())
            letters = ''.join(char for char in filtered_text if char.isalpha() and char.isupper())
            numbers = ''.join(char for char in filtered_text if char.isdigit())

            # Procesar letras y números
            if len(numbers) == 3:
                number_samples.append(numbers)
                if len(number_samples) > sample_limit:
                    number_samples.pop(0)

            if len(letters) == 3:
                letter_samples.append(letters)
                if len(letter_samples) > sample_limit:
                    letter_samples.pop(0)

            # Confirmar formato completo si hay suficientes muestras
            if len(number_samples) >= sample_limit and len(letter_samples) >= sample_limit:
                most_common_numbers = Counter(number_samples).most_common(1)
                most_common_letters = Counter(letter_samples).most_common(1)

                if most_common_numbers and most_common_letters:
                    new_plate = f"{most_common_letters[0][0]} {most_common_numbers[0][0]}"

                    # Confirmar placa solo si el formato es nuevo
                    if new_plate != confirmed_plate:
                        if new_plate == pending_plate:
                            pending_count += 1
                            if pending_count >= confirmation_threshold:
                                confirmed_plate = new_plate
                                print(f"Placa detectada: {confirmed_plate}")
                                pending_count = 0
                        else:
                            pending_plate = new_plate
                            pending_count = 1

        except Exception as e:
            print(f"Error en OCR: {e}")

# Inicia el hilo de OCR
ocr_thread = threading.Thread(target=process_ocr, daemon=True)
ocr_thread.start()

# Inicia el proceso de ffmpeg
process = start_ffmpeg_process()

while True:
    try:
        # Leer el cuadro de video
        in_bytes = process.stdout.read(width * height * 3)
        if not in_bytes:
            raise ValueError("No se pudo obtener el frame.")
        
        # Convertir a imagen numpy
        frame = np.frombuffer(in_bytes, np.uint8).reshape([height, width, 3])

        # Crear una copia de 'frame' para dibujar el ROI y no alterar el original
        frame_copy = frame.copy()
        
        # Dibujar el ROI
        cv2.rectangle(frame_copy, (roi_x, roi_y), (roi_x + roi_w, roi_y + roi_h), (0, 255, 0), 2)

        # Detectar amarillo en la imagen
        hsv = cv2.cvtColor(frame_copy, cv2.COLOR_BGR2HSV)
        lower_yellow = np.array([20, 100, 100])  # Rango para detectar amarillo
        upper_yellow = np.array([30, 255, 255])
        mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)
        masked_yellow = cv2.bitwise_and(frame_copy, frame_copy, mask=mask_yellow)

        # Verificar si hay amarillo en el ROI
        roi = mask_yellow[roi_y:roi_y+roi_h, roi_x:roi_x+roi_w]
        if cv2.countNonZero(roi) > 500:  # Ajusta el umbral de detección
            # Enviar el ROI al hilo de OCR si no está lleno
            if ocr_queue.qsize() < 5:
                roi_image = frame[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]
                ocr_queue.put(roi_image)

        # Mostrar la placa confirmada en el video
        cv2.putText(frame_copy, f"Placa: {confirmed_plate}", (roi_x, roi_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        # Mostrar frame con máscara y texto
        cv2.imshow("Transmisión en Vivo", frame_copy)
        cv2.imshow("Detección de Amarillo", masked_yellow)

        # Salir al presionar 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    except Exception as e:
        print(f"Error: {e}. Reintentando en 5 segundos...")
        process.terminate()
        time.sleep(5)
        process = start_ffmpeg_process()

# Finalizar
ocr_queue.put(None)  # Detener el hilo
process.terminate()
cv2.destroyAllWindows()
