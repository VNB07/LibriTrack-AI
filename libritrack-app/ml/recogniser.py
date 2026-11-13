"""Face embeddings and book cover matching.
Modularized for two-stage Borrow Mode and continuous Attendance Mode with strict geometric validation.
"""
import os
import numpy as np

try:
    import face_recognition
    FACE_AVAILABLE = True
except ImportError:
    FACE_AVAILABLE = False

try:
    import cv2
    CV_AVAILABLE = True
except ImportError:
    CV_AVAILABLE = False

THRESHOLD = 0.5
MIN_BOOK_MATCHES = 16  # Higher threshold to prevent false positives on faces or background patterns


def _require_face():
    if not FACE_AVAILABLE:
        raise RuntimeError("face_recognition is not installed.")


def _require_cv():
    if not CV_AVAILABLE:
        raise RuntimeError("opencv-python is not installed.")


def embedding_from_file(path: str):
    """Return the face embedding if the photo has exactly one face, else None."""
    _require_face()
    image = face_recognition.load_image_file(path)
    locations = face_recognition.face_locations(image)
    if len(locations) != 1:
        return None
    return face_recognition.face_encodings(image, locations)[0].tolist()


def extract_and_save_book_features(image_path: str, save_path: str) -> bool:
    """Extracts ORB keypoints and descriptors for a book cover and saves them to .npz."""
    _require_cv()
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return False
    orb = cv2.ORB_create(nfeatures=2500, scaleFactor=1.2, nlevels=8)
    keypoints, descriptors = orb.detectAndCompute(img, None)
    if descriptors is None or len(descriptors) < MIN_BOOK_MATCHES:
        return False

    pts = np.array([kp.pt for kp in keypoints], dtype=np.float32)
    np.savez_compressed(save_path, pts=pts, des=descriptors, shape=img.shape[:2])
    return True


def identify_face_only(frame_path: str, face_gallery: list) -> dict:
    """Stage 1: Detects and recognizes unoccluded faces in the frame."""
    _require_face()
    image = face_recognition.load_image_file(frame_path)
    height, width = image.shape[:2]
    locations = face_recognition.face_locations(image)
    encodings = face_recognition.face_encodings(image, locations)

    faces = []
    for box, encoding in zip(locations, encodings):
        best_id, best_distance = None, 1.0
        for student_id, embeddings in face_gallery:
            distance = face_recognition.face_distance(np.array(embeddings), encoding).min()
            if distance < best_distance:
                best_id, best_distance = student_id, distance
        if best_distance > THRESHOLD:
            best_id = None
        faces.append({"student_id": best_id, "box": [int(v) for v in box], "confidence": float(1.0 - best_distance)})

    return {"width": int(width), "height": int(height), "faces": faces}


def _is_valid_book_quadrilateral(corners: np.ndarray, frame_w: int, frame_h: int) -> bool:
    """Validates that transformed 4 corners form a realistic, non-collapsed, convex rectangle."""
    pts = corners.reshape(4, 2)
    xs = pts[:, 0]
    ys = pts[:, 1]

    # Check bounds
    if np.any(xs < -50) or np.any(xs > frame_w + 50) or np.any(ys < -50) or np.any(ys > frame_h + 50):
        return False

    width = np.max(xs) - np.min(xs)
    height = np.max(ys) - np.min(ys)

    # Must be at least 100x100 pixels and smaller than 95% of frame
    if width < 100 or height < 100 or width > frame_w * 0.98 or height > frame_h * 0.98:
        return False

    # Aspect ratio check: standard books are between 0.45 and 2.2
    aspect = width / float(height)
    if aspect < 0.45 or aspect > 2.2:
        return False

    # Convexity check: cross products between sequential edges must share the same sign
    def cross_2d(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    signs = [
        cross_2d(pts[0], pts[1], pts[2]) > 0,
        cross_2d(pts[1], pts[2], pts[3]) > 0,
        cross_2d(pts[2], pts[3], pts[0]) > 0,
        cross_2d(pts[3], pts[0], pts[1]) > 0,
    ]
    if not (all(signs) or not any(signs)):
        return False

    return True


def identify_book_only(frame_path: str, book_gallery: list) -> dict:
    """Stage 2: Focuses full frame processing on detecting registered book covers with strict geometry checks."""
    _require_cv()
    frame_gray = cv2.imread(frame_path, cv2.IMREAD_GRAYSCALE)
    if frame_gray is None:
        return {"width": 0, "height": 0, "books": []}

    height, width = frame_gray.shape[:2]
    if not book_gallery:
        return {"width": int(width), "height": int(height), "books": []}

    orb = cv2.ORB_create(nfeatures=2500, scaleFactor=1.2, nlevels=8)
    frame_kps, frame_des = orb.detectAndCompute(frame_gray, None)
    if frame_des is None or len(frame_des) == 0:
        return {"width": int(width), "height": int(height), "books": []}

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    detected_books = []

    for item in book_gallery:
        barcode = item["barcode"]
        book_des = item["des"]
        book_shape = item["shape"]

        if book_des is None or len(book_des) < MIN_BOOK_MATCHES:
            continue

        try:
            matches = matcher.knnMatch(book_des, frame_des, k=2)
        except Exception:
            continue

        good_matches = []
        for m_tuple in matches:
            if len(m_tuple) == 2:
                m, n = m_tuple
                if m.distance < 0.75 * n.distance:  # Stricter Lowe's ratio test
                    good_matches.append(m)

        if len(good_matches) >= MIN_BOOK_MATCHES:
            src_pts = np.float32([item["pts"][m.queryIdx] for m in good_matches]).reshape(-1, 1, 2)
            dst_pts = np.float32([frame_kps[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

            H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 4.0)
            if H is not None and mask is not None:
                inliers_count = int(np.sum(mask))
                if inliers_count >= MIN_BOOK_MATCHES:
                    h, w = book_shape
                    corners = np.float32([[0, 0], [0, h - 1], [w - 1, h - 1], [w - 1, 0]]).reshape(-1, 1, 2)
                    transformed_corners = cv2.perspectiveTransform(corners, H)

                    if _is_valid_book_quadrilateral(transformed_corners, width, height):
                        xs = transformed_corners[:, 0, 0]
                        ys = transformed_corners[:, 0, 1]
                        left, right = int(np.min(xs)), int(np.max(xs))
                        top, bottom = int(np.min(ys)), int(np.max(ys))

                        detected_books.append({
                            "barcode": barcode,
                            "box": [max(0, top), min(width, right), min(height, bottom), max(0, left)],
                            "matches": inliers_count
                        })

    return {"width": int(width), "height": int(height), "books": detected_books}


def identify_in_frame(frame_path: str, face_gallery: list, book_gallery: list) -> dict:
    face_res = identify_face_only(frame_path, face_gallery)
    book_res = identify_book_only(frame_path, book_gallery)
    return {
        "width": face_res["width"],
        "height": face_res["height"],
        "faces": face_res["faces"],
        "books": book_res["books"]
    }