import cv2
import numpy as np
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect

def unsharp_mask(image, kernel_size=(5,5), sigma=1.0, amount=2.0, threshold=0):
    blurred = cv2.GaussianBlur(image, kernel_size, sigma)
    sharpened = float(amount + 1) * image - float(amount) * blurred
    sharpened = np.clip(sharpened, 0, 255).astype(np.uint8)
    if threshold > 0:
        low_contrast_mask = np.abs(image - blurred) < threshold
        np.copyto(sharpened, image, where=low_contrast_mask)
    return sharpened

def advanced_preprocessing(image_bgr):
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    # 🎯 ¡Más suave! - quitamos clahe y sharpening agresivo
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    # 🔍 Threshold adaptativo pero SUAVE
    adapt = cv2.adaptiveThreshold(blur, 255,
                                  cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                  cv2.THRESH_BINARY_INV, 31, 10)

    # 🔧 Morfología ligera (cerrar huequitos sin dañar letras)
    kernel = np.ones((2, 2), np.uint8)
    closed = cv2.morphologyEx(adapt, cv2.MORPH_CLOSE, kernel, iterations=1)

    return closed


def auto_crop_plate(bin_img, gap_threshold=0.1, min_gap_rows=20):
    h, w = bin_img.shape
    consecutive_gap = 0
    cut_line = h
    for row in range(h - 1, -1, -1):
        whites = cv2.countNonZero(bin_img[row:row+1, :])
        if whites < gap_threshold * w:
            consecutive_gap += 1
        else:
            consecutive_gap = 0
        if consecutive_gap >= min_gap_rows:
            cut_line = row + min_gap_rows
            break
    return bin_img[:cut_line, :]

def detectar_placa_desde_imagen(path_imagen):
    print(f"\n🔍 Procesando imagen: {path_imagen}")
    image = cv2.imread(path_imagen)
    if image is None:
        print("❌ No se pudo cargar la imagen.")
        return

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 200)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    plate_candidate = None
    max_area = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 1000:
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            if len(approx) == 4 and area > max_area:
                max_area = area
                plate_candidate = approx

    if plate_candidate is None:
        print("❗ No se encontró ningún contorno válido.")
        return

    image_with_contour = image.copy()
    cv2.drawContours(image_with_contour, [plate_candidate], -1, (0, 255, 0), 2)
    cv2.imshow("1️⃣ Imagen con placa detectada", image_with_contour)

    pts = plate_candidate.reshape(4, 2)
    rect = order_points(pts)

    width = np.linalg.norm(rect[0] - rect[1])
    height = np.linalg.norm(rect[0] - rect[3])
    print(f"📐 Tamaño placa: ancho={int(width)}, alto={int(height)}")

    if width < 80 or height < 25:
        print("⚠️ Placa demasiado pequeña para OCR.")
        return

    W, H = 300, 100
    dst = np.array([[0, 0], [W-1, 0], [W-1, H-1], [0, H-1]], dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    rectified = cv2.warpPerspective(image, M, (W, H))
    cv2.imshow("2️⃣ Placa recortada (sin procesar)", rectified)

    # Recorte opcional para eliminar texto inferior ("BARRANQUILLA")
    cropped = rectified[:int(H * 0.8), :]
    cv2.imshow("3️⃣ Placa recortada (directa sin procesamiento)", cropped)

    # Escalar para mejorar lectura OCR
    scaled = cv2.resize(cropped, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    # OCR sin procesamiento destructivo
    config_tess = "--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    detected_text = pytesseract.image_to_string(scaled, config=config_tess).strip()
    filtered_text = "".join(c for c in detected_text if c.isalnum()).upper()

    print("📷 OCR crudo:", detected_text)
    print("🔤 Filtrado:", filtered_text)

    letras = "".join(c for c in filtered_text if c.isalpha())[:3]
    numeros = "".join(c for c in filtered_text if c.isdigit())[:3]

    if len(letras) == 3 and len(numeros) == 3:
        placa_final = f"{letras} {numeros}"
        print(f"✅ Placa detectada: {placa_final}")
    else:
        print("❗ No se pudo detectar una placa válida.")

    cv2.waitKey(0)
    cv2.destroyAllWindows()


# ========================
# PRUEBA
# ========================
detectar_placa_desde_imagen("D:/Proyecto_Final/Proyecto_Final/FinalProyect/scripts/imagen.png")
