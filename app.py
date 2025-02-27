from flask import Flask, Response
import face_recognition
import cv2
import numpy as np
from picamera2 import Picamera2
import time, pickle

app = Flask(__name__)

# Initialize the camera once.
picam2 = Picamera2()
picam2.configure(picam2.create_preview_configuration(
    main={"format": 'XRGB8888', "size": (1920, 1080)}
))
picam2.start()

# Load known face encodings
with open("encodings.pickle", "rb") as f:
    data = pickle.loads(f.read())
known_face_encodings = data["encodings"]
known_face_names = data["names"]

# Face recognition variables
face_locations = []
face_encodings = []
face_names = []
recent_faces = {}
CACHE_EXPIRATION = 10  # seconds
cv_scaler = 4

def process_frame(frame):
    global face_locations, face_encodings, face_names

    print("[DEBUG] Processing frame...")

    # Resize the frame using cv_scaler to increase performance
    resized_frame = cv2.resize(frame, (0, 0), fx=(1/cv_scaler), fy=(1/cv_scaler))
    print("[DEBUG] Frame resized.")

    # Convert the image from BGR to RGB colour space
    rgb_resized_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
    print("[DEBUG] Frame converted to RGB.")

    # Find all the faces and face encodings in the current frame of video
    face_locations = face_recognition.face_locations(rgb_resized_frame)
    face_encodings = face_recognition.face_encodings(rgb_resized_frame, face_locations, model='large')
    print(f"[DEBUG] Found {len(face_locations)} face(s).")

    face_names = []
    for face_encoding in face_encodings:
        # See if the face is a match for the known face(s)
        matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
        name = "Unknown"
        type_of_enter = "guest"

        # Use the known face with the smallest distance to the new face if matches are found
        face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
        if face_distances.size > 0:  # Check if face_distances is not empty
            best_match_index = np.argmin(face_distances)
            if matches[best_match_index]:
                name = known_face_names[best_match_index]
                type_of_enter = "resident"

        # Avoid sending duplicate data within the CACHE_EXPIRATION window
        current_time = time.time()
        if name not in recent_faces or (current_time - recent_faces[name]) > CACHE_EXPIRATION:
            print(f"[DEBUG] Sending data for {name}.")
            send_to_server(name, type_of_enter)
            recent_faces[name] = current_time
        else:
            print(f"[DEBUG] Skipping sending data for {name}, recently sent.")

        face_names.append(name)

    return frame

def draw_results(frame):
    # Display the results
    for (top, right, bottom, left), name in zip(face_locations, face_names):
        # Scale back up face locations since the frame we detected in was scaled
        top *= cv_scaler
        right *= cv_scaler
        bottom *= cv_scaler
        left *= cv_scaler

        # Draw a box around the face
        cv2.rectangle(frame, (left, top), (right, bottom), (244, 42, 3), 3)

        # Draw a label with a name below the face
        cv2.rectangle(frame, (left -3, top - 35), (right+3, top), (244, 42, 3), cv2.FILLED)
        font = cv2.FONT_HERSHEY_DUPLEX
        cv2.putText(frame, name, (left + 6, top - 6), font, 1.0, (255, 255, 255), 1)

    return frame
def generate_frames():
    while True:
        # Capture a frame
        frame = picam2.capture_array()

        # Face recognition
        processed_frame = process_frame(frame)
        display_frame = draw_results(processed_frame)

        cv2.imshow('Video', display_frame)

        # Break the loop and stop the script if 'q' is pressed
        if cv2.waitKey(1) == ord("q"):
            print("[INFO] Quitting...")
            break

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index():
    return "<h1>Pi Camera Face Rec Feed</h1><img src='/video_feed'>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
