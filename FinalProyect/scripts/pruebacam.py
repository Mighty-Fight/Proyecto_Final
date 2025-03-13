import cv2

rtsp_url = "rtsp://admin:abcd1234..@186.119.52.250:554/Streaming/Channels/101"

cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"H264"))  # Fuerza H.264



if not cap.isOpened():
    print("❌ No se  pudo conectar a la cámara. Verifica la URL RTSP.")
else:
    print("✅ Conexión a la cámara establecida.")

while True:
    ret, frame = cap.read()
    if not ret:
        print("⚠️ No se pudo obtener frame. Intentando nuevamente...")
        break

    cv2.imshow("Transmisión RTSP", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
