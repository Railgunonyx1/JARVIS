"""Face identity recognition for JARVIS MK-X.

Uses DeepFace for periodic identity verification (not continuous — too slow for real-time).
Runs every N seconds to check if the user is present and who they are.

Face DB stored as pickle files in vision/face_db/.
"""

import os
import time
import pickle
import logging
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger("jarvis.vision.face")

FACE_DB_DIR = Path(__file__).resolve().parent / "face_db"

try:
    from deepface import DeepFace
    DEEPFACE_AVAILABLE = True
except ImportError:
    DEEPFACE_AVAILABLE = False
    logger.warning("deepface not installed — face identity unavailable")


@dataclass
class FaceResult:
    """Result from face identity check."""
    name: str  # "unknown" or registered name
    confidence: float
    emotion: Optional[str] = None  # if emotion analysis enabled
    age: Optional[int] = None
    is_owner: bool = False


class FaceIdentity:
    """Periodic face identity verification using DeepFace."""

    def __init__(
        self,
        check_interval: float = 5.0,
        recognition_model: str = "VGG-Face",
        enforce_detection: bool = False,
        owner_name: str = "Aayan",
    ):
        self._check_interval = check_interval
        self._recognition_model = recognition_model
        self._enforce_detection = enforce_detection
        self._owner_name = owner_name
        self._last_check = 0.0
        self._last_result: Optional[FaceResult] = None
        self._encoding_cache: dict = {}

        # Ensure face DB directory exists
        FACE_DB_DIR.mkdir(exist_ok=True)

        # Load existing encodings
        self._load_db()

        if not DEEPFACE_AVAILABLE:
            logger.warning("FaceIdentity: deepface not available, face recognition disabled")

    @property
    def available(self) -> bool:
        return DEEPFACE_AVAILABLE

    def check(self, frame: np.ndarray, force: bool = False) -> Optional[FaceResult]:
        """Check face in frame. Respects check_interval unless force=True."""
        if not self.available or frame is None:
            return None

        now = time.time()
        if not force and (now - self._last_check) < self._check_interval:
            return self._last_result

        self._last_check = now

        try:
            result = self._identify(frame)
            self._last_result = result
            if result:
                logger.info("Face: %s (%.0f%%)", result.name, result.confidence * 100)
            return result
        except Exception as e:
            logger.debug("Face check error: %s", e)
            return None

    def enroll(self, frame: np.ndarray, name: str) -> bool:
        """Enroll a face from a frame. Returns True on success."""
        if not self.available:
            return False

        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            # DeepFace.represent returns embeddings
            # DeepFace.represent expects an image path or array; write temp file for reliability
            temp_path = str(FACE_DB_DIR / "_temp_enroll.jpg")
            cv2.imwrite(temp_path, frame)
            representations = DeepFace.represent(
                img_path=temp_path,
                model_name=self._recognition_model,
                enforce_detection=self._enforce_detection,
            )
            if os.path.exists(temp_path):
                os.remove(temp_path)

            if not representations:
                logger.warning("No face found in enrollment frame")
                return False

            embedding = representations[0]["embedding"]

            # Save to DB
            person_path = FACE_DB_DIR / f"{name}.pkl"
            with open(person_path, "wb") as f:
                pickle.dump({
                    "name": name,
                    "embedding": embedding,
                    "model": self._recognition_model,
                    "enrolled_at": time.time(),
                }, f)

            self._encoding_cache[name] = embedding
            logger.info("Enrolled face: %s", name)
            return True

        except Exception as e:
            logger.error("Enrollment failed: %s", e)
            return False

    def _identify(self, frame: np.ndarray) -> Optional[FaceResult]:
        """Identify face in frame against enrolled database."""
        if not self._encoding_cache:
            # No enrolled faces — just detect emotion/age
            return self._analyze_only(frame)

        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Use DeepFace.find for recognition
            temp_path = str(FACE_DB_DIR / "_temp.jpg")
            cv2.imwrite(temp_path, frame)

            results = DeepFace.find(
                img_path=temp_path,
                db_path=str(FACE_DB_DIR),
                model_name=self._recognition_model,
                enforce_detection=self._enforce_detection,
                silent=True,
            )

            # Clean up temp
            if os.path.exists(temp_path):
                os.remove(temp_path)

            if results and len(results) > 0 and not results[0].empty:
                best = results[0].iloc[0]
                name = Path(best["identity"]).stem
                # Distance is cosine similarity — lower is better
                dist = best.get("VGG-Face_cosine", best.get("embedding_cosine", 1.0))
                confidence = max(0, 1 - dist)

                return FaceResult(
                    name=name,
                    confidence=confidence,
                    is_owner=(name == self._owner_name),
                )
            else:
                return FaceResult(name="unknown", confidence=0.0)

        except Exception as e:
            logger.debug("Identification error: %s", e)
            return self._analyze_only(frame)

    def _analyze_only(self, frame: np.ndarray) -> Optional[FaceResult]:
        """Analyze face without identity matching (emotion + age)."""
        try:
            temp_path = str(FACE_DB_DIR / "_temp_analyze.jpg")
            cv2.imwrite(temp_path, frame)
            analysis = DeepFace.analyze(
                img_path=temp_path,
                actions=["emotion", "age"],
                enforce_detection=self._enforce_detection,
                silent=True,
            )
            if os.path.exists(temp_path):
                os.remove(temp_path)

            if analysis:
                result = analysis[0] if isinstance(analysis, list) else analysis
                return FaceResult(
                    name="detected",
                    confidence=0.8,
                    emotion=result.get("dominant_emotion"),
                    age=result.get("age"),
                )
        except Exception as e:
            logger.debug("Face analysis error: %s", e)

        return None

    def _load_db(self):
        """Load all enrolled face encodings."""
        for pkl_file in FACE_DB_DIR.glob("*.pkl"):
            if pkl_file.name.startswith("_"):
                continue
            try:
                with open(pkl_file, "rb") as f:
                    data = pickle.load(f)
                self._encoding_cache[data["name"]] = data["embedding"]
                logger.info("Loaded face encoding: %s", data["name"])
            except Exception as e:
                logger.warning("Failed to load face DB %s: %s", pkl_file.name, e)

    def list_enrolled(self) -> List[str]:
        """List all enrolled face names."""
        return list(self._encoding_cache.keys())

    @property
    def last_result(self) -> Optional[FaceResult]:
        return self._last_result

    @property
    def check_interval(self) -> float:
        return self._check_interval

    @check_interval.setter
    def check_interval(self, value: float):
        self._check_interval = max(1.0, value)
