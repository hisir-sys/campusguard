"""Video preprocessing adapted from the supplied MC3 fight-detection reference."""
import cv2
import numpy as np

MEAN = np.array([0.43216, 0.394666, 0.37645], dtype=np.float32)
STD = np.array([0.22803, 0.22145, 0.216989], dtype=np.float32)


def preprocess_frame(frame_bgr):
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    # Equivalent target geometry to the reference: resize 128x171, center crop 112x112.
    resized = cv2.resize(rgb, (171, 128), interpolation=cv2.INTER_LINEAR)
    y0, x0 = (128 - 112) // 2, (171 - 112) // 2
    crop = resized[y0:y0 + 112, x0:x0 + 112]
    arr = crop.astype(np.float32) / 255.0
    arr = (arr - MEAN) / STD
    return arr


def make_clip(frames):
    """Return a torch-ready [1, 3, T, 112, 112] numpy array."""
    processed = [preprocess_frame(f) for f in frames]
    arr = np.stack(processed, axis=0)  # T,H,W,C
    return np.transpose(arr, (3, 0, 1, 2))[None, ...].astype(np.float32)
