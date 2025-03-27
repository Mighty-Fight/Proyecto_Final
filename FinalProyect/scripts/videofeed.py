from flask import Flask, Response
import cv2

app = Flask(__name__)

# URL de tu cámara RTSP
RTSP_URL = "rtsp://admin:abcd1234..@181.236.149.17:554/Streaming/Channels/101"

def generate_frames():
    cap = cv2.VideoCapture(RTSP_URL)
    if not cap.isOpened():
        print("❌ No se pudo conectar a la cámara.")
        return

    while True:
        success, frame = cap.read()
        if not success:
            continue

        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue

        frame_bytes = buffer.tobytes()
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")

@app.route("/trasmisión")
def video_feed():
    return Response(generate_frames(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
