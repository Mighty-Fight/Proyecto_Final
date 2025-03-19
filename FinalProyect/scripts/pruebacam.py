import cv2

rtsp_url = "rtsp://admin:abcd1234..@181.236.141.192:554/Streaming/Channels/101"
cap = cv2.VideoCapture(rtsp_url)

if not cap.isOpened():
    print("❌ No se pudo conectar a la cámara. Verifica la URL RTSP o la conexión de red.")
else:
    print("✅ Conexión a la cámara establecida.")

cap.release()
