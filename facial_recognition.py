import RPi.GPIO as GPIO
import time
import face_recognition
import cv2
import numpy as np
from picamera2 import Picamera2
import pickle
import requests
from inference import get_model
import supervision as sv
from collections import deque
from roboflow import Roboflow
import os

RELAY_PIN = 17  # Controls the electric strike lock
# Fix: Cleanup any previous GPIO usage
GPIO.cleanup()




GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_PIN, GPIO.OUT)
GPIO.output(RELAY_PIN, GPIO.LOW)

api_key="$$$$$$$$$"
# Initialize the Roboflow object with your API key
rf = Roboflow(api_key=api_key)

# Retrieve your workspace and project (update with your actual workspace and project)
workspaceId = 'rpi5smart-lock-door'
projectId = 'od-jffd8-oky8i'
project = rf.workspace(workspaceId).project(projectId)
# ---------------- Global Configuration and Variables ----------------

cv_scaler = 2  # Factor to downscale frames for performance

# Known face data (populate these with your known faces)
known_face_encodings = []  # List of known face encodings
known_face_names = []      # Corresponding list of names

# Cache to avoid sending duplicate data within CACHE_EXPIRATION seconds
recent_faces = {}
CACHE_EXPIRATION = 60  # seconds; adjust as needed

# Buffer to store frames with timestamps (for a 5-second window)
frame_buffer = deque()
# Global holder for an unknown face event
unknown_event = None

# ---------------- Load Roboflow Online Model ----------------
# Load your pre-trained YOLOv8 model from Roboflow
rf_model = get_model(model_id="od-jffd8-oky8i/3",api_key=api_key)
# Load pre-trained face encodings
print("[INFO] loading encodings...")
with open("encodings.pickle", "rb") as f:
    data = pickle.loads(f.read())
known_face_encodings = data["encodings"]
known_face_names = data["names"]

# Initialize the camera
print("[INFO] initializing camera...")
picam2 = Picamera2()
picam2.configure(picam2.create_preview_configuration(main={"format": 'XRGB8888', "size": (1920, 1080)}))
picam2.start()
print("[INFO] camera started...")

# Initialize our variables
cv_scaler = 4 # this has to be a whole number

face_locations = []
face_encodings = []
face_names = []
frame_count = 0
start_time = time.time()
fps = 0

# Server URL
SERVER_URL = "$$$$$$$$$$$$$$"

# Cache for recent face detections to avoid repeated POSTs
recent_faces = {}
CACHE_EXPIRATION = 10  # seconds

import pyimgur  # Install this for Imgur support

IMGUR_CLIENT_ID = "$$$$$$$$$$$$$"  # Replace with your Imgur client ID
def activate_lock():
    print("Unlocking lock through relay...")
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(RELAY_PIN, GPIO.OUT)
    # Turn on relay (powers buzzer via 5V)
    GPIO.output(RELAY_PIN, GPIO.HIGH)
    time.sleep(5)  # Keep buzzer on for 3 seconds
    
    # Turn off relay (stops buzzer)
    GPIO.output(RELAY_PIN, GPIO.LOW)
    print("Locked")
    
def upload_to_imgur(image_path):
    try:
        im = pyimgur.Imgur(IMGUR_CLIENT_ID)
        uploaded_image = im.upload_image(image_path, title="Captured Frame")
        print(f"[INFO] Image uploaded: {uploaded_image.link}")
        return uploaded_image.link
    except Exception as e:
        print(f"[ERROR] Failed to upload image: {e}")
        return None

import os

# Define a directory to store captured image

IMAGE_SAVE_DIR = "captured_images"

# Ensure the directory exists
os.makedirs(IMAGE_SAVE_DIR, exist_ok=True)

def send_to_server(name, type_of_enter, frame):
    # Save the frame to the project directory
    temp_image_path = os.path.join(IMAGE_SAVE_DIR, "captured_frame.jpg")
    cv2.imwrite(temp_image_path, frame)

    # Upload to Imgur or your preferred service
    image_url = upload_to_imgur(temp_image_path)

    if not image_url:
        print("[ERROR] Failed to upload image, skipping sending to server.")
        return

    payload = {"name": name, "typeOfEnter": type_of_enter, "tags": [], "imageURL": image_url}
    try:
        response = requests.post(SERVER_URL, json=payload)
        print(f"[INFO] Sent data to server: {payload}, Response: {response.status_code}")
    except Exception as e:
        print(f"[ERROR] Failed to send data: {e}")
        
def classify_unknown_frame_online(frame):
    """
    Runs online inference on a frame using the Roboflow model.
    Converts the result into a supervision Detections object and returns
    the number of detections (i.e. the length of the predictions array).
    """
    results = rf_model.infer(frame)[0]
    detections = sv.Detections.from_inference(results)
    # Assume detections.xyxy is a numpy array of shape (N, 4) where N is the number of detections.
    print(detections)
    count = len(detections.xyxy) if detections.xyxy is not None else 0
    return count


def process_frame(frame):
    global unknown_event, frame_buffer, recent_faces

    current_time = time.time()

    # Add the current frame with its timestamp to the buffer
    frame_buffer.append((current_time, frame.copy()))
    # Remove frames older than 5 seconds from the buffer
    while frame_buffer and (current_time - frame_buffer[0][0] > 5):
        frame_buffer.popleft()

    print("[DEBUG] Processing frame...")

    # Resize the frame for performance
    resized_frame = cv2.resize(frame, (0, 0), fx=(1 / cv_scaler), fy=(1 / cv_scaler))
    print("[DEBUG] Frame resized.")

    # Convert the image from BGR to RGB color space
    rgb_resized_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
    print("[DEBUG] Frame converted to RGB.")

    # Find all faces and compute face encodings in the current frame
    face_locations = face_recognition.face_locations(rgb_resized_frame)
    face_encodings = face_recognition.face_encodings(rgb_resized_frame, face_locations, model='large')
    print(f"[DEBUG] Found {len(face_locations)} face(s).")

    face_names = []

    for face_encoding in face_encodings:
        # See if the face is a match for the known face(s)
        matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
        name = "Unknown"
        type_of_enter = "guest"  # Default type for unknown faces

        # Use the known face with the smallest distance to the new face if matches are found
        face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
        if face_distances.size > 0:
            best_match_index = np.argmin(face_distances)
            if matches[best_match_index]:
                name = known_face_names[best_match_index]
                type_of_enter = "resident"
                try:
                    activate_lock()
                finally:
                    GPIO.cleanup()


        # Process known faces immediately (if not recently sent)
        if name != "Unknown":
            if name not in recent_faces or (current_time - recent_faces[name]) > CACHE_EXPIRATION:
                print(f"[DEBUG] Sending data for {name}.")
                send_to_server(name, type_of_enter, frame)
                recent_faces[name] = current_time
            else:
                print(f"[DEBUG] Skipping sending data for {name}, recently sent.")
        else:
            # For unknown faces, if not recently processed, initiate an unknown event.
            if "Unknown" not in recent_faces or (current_time - recent_faces["Unknown"]) > CACHE_EXPIRATION:
                if unknown_event is None:
                    # Capture all frames from the last 5 seconds as "before" frames.
                    before_frames = [frm for ts, frm in list(frame_buffer)]
                    unknown_event = {
                        "trigger_time": current_time,
                        "before_frames": before_frames,
                        "after_frames": []  # To be collected in the next 5 seconds
                    }
                    print("[DEBUG] Started unknown event. Captured 5 seconds before frames.")
                # While within 5 seconds after the trigger, add current frames as "after" frames.
                if current_time <= unknown_event["trigger_time"] + 5:
                    unknown_event["after_frames"].append(frame.copy())
                    print(f"[DEBUG] Added frame to unknown event after_frames (Count: {len(unknown_event['after_frames'])}).")
            else:
                print("[DEBUG] Skipping unknown event due to recent cache for Unknown.")

        face_names.append(name)

    # Check if an unknown event is active and the 5-second after-window is complete
    if unknown_event is not None and time.time() > unknown_event["trigger_time"] + 5:
        # Combine frames from before and after the unknown event trigger
        combined_frames = unknown_event["before_frames"] + unknown_event["after_frames"]
        print(f"[DEBUG] Processing unknown event with {len(combined_frames)} frames.")

        delivery_detected = False
        # Run online inference on each frame in the combined set
        for idx, f in enumerate(combined_frames):
            detection_count = classify_unknown_frame_online(f)
            print(f"[DEBUG] Frame {idx} detection count: {detection_count}")
            if detection_count >= 2:
                delivery_detected = True
                break
        
        if delivery_detected:
            type_of_enter = "delivery"
            print("[DEBUG] Delivery detected in unknown event frames.")
        else:
            type_of_enter = "unknown"
            print("[DEBUG] No delivery detected in unknown event frames.")
            # Upload each combined frame to your Roboflow project for annotation without tagging
            for idx, f in enumerate(combined_frames):
                # Save the frame temporarily
                temp_filename = f"upload_frame_{int(time.time())}_{idx}.jpg"
                cv2.imwrite(temp_filename, f)
                print(f"[DEBUG] Uploading {temp_filename} to Roboflow for annotation.")
                project.upload(image_path=temp_filename,num_retry_uploads=3)

        # Send the result for the unknown face event to the server
        send_to_server("N/A", type_of_enter, frame)
        recent_faces["Unknown"] = time.time()
        unknown_event = None  # Reset the unknown event

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

def calculate_fps():
    global frame_count, start_time, fps
    frame_count += 1
    elapsed_time = time.time() - start_time
    if elapsed_time > 1:
        fps = frame_count / elapsed_time
        frame_count = 0
        start_time = time.time()
    return fps

while True:
    try:
        # Capture a frame from camera
        frame = picam2.capture_array()

        # Process the frame with the function
        processed_frame = process_frame(frame)

        # Get the text and boxes to be drawn based on the processed frame
        display_frame = draw_results(processed_frame)

        # Calculate and update FPS
        current_fps = calculate_fps()

        # Attach FPS counter to the text and boxes
        cv2.putText(display_frame, f"FPS: {current_fps:.1f}", (display_frame.shape[1] - 150, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        # Display everything over the video feed.
        cv2.imshow('Video', display_frame)

        # Break the loop and stop the script if 'q' is pressed
        if cv2.waitKey(1) == ord("q"):
            print("[INFO] Quitting...")
            break

    except Exception as e:
        print(f"[ERROR] Exception in main loop: {e}")

# ---------------- Cleanup ----------------
cv2.destroyAllWindows()
picam2.stop()
GPIO.cleanup()
print("[INFO] Camera & GPIO cleaned up.")