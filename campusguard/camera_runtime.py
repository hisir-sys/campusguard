from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from urllib.parse import quote, urlsplit, urlunsplit

import cv2
from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtGui import QImage

from campusguard.ai_pipeline import VisionPipeline
from campusguard.footage import FightFootageRecorder
from campusguard.storage import application_data_dir
from campusguard.credentials import CredentialVault
from campusguard.settings import AppSettings, CameraConfig, CameraCredentials

try:
    cv2.setLogLevel(cv2.LOG_LEVEL_ERROR)
except (AttributeError, cv2.error):
    pass


def build_capture_source(
    source_type: str,
    source_address: str,
    credentials: CameraCredentials | None = None,
) -> int | str:
    source_type = source_type.upper()
    address = source_address.strip()
    credentials = credentials or CameraCredentials()

    if source_type == "USB":
        if credentials.username or credentials.password:
            raise ValueError("USB camera sources do not use username or password fields.")
        try:
            index = int(address)
        except ValueError as error:
            raise ValueError("Enter a USB camera device index, such as 1.") from error
        if index < 0:
            raise ValueError("USB device index must be zero or greater.")
        return index

    if source_type == "IP" and "://" not in address:
        address = f"http://{address}"
    elif source_type in {"HTTP", "MJPEG"} and "://" not in address:
        address = f"http://{address}"

    parsed = urlsplit(address)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(
            "Do not put credentials inside the camera URL. Enter them in the separate username and password fields."
        )
    if source_type == "RTSP" and parsed.scheme.lower() not in {"rtsp", "rtsps"}:
        raise ValueError("RTSP sources must use an rtsp:// or rtsps:// address.")
    if source_type in {"HTTP", "MJPEG", "IP"} and parsed.scheme.lower() not in {
        "http", "https", "rtsp", "rtsps"
    }:
        raise ValueError("Enter an HTTP, HTTPS, RTSP, or RTSPS camera address.")
    if not parsed.netloc:
        raise ValueError("The camera source address is incomplete.")

    if credentials.username or credentials.password:
        host = parsed.netloc.rsplit("@", 1)[-1]
        user = quote(credentials.username, safe="")
        password = quote(credentials.password, safe="")
        auth = user if not password else f"{user}:{password}"
        parsed = parsed._replace(netloc=f"{auth}@{host}")

    return urlunsplit(parsed)



def enumerate_local_cameras(max_devices: int = 10) -> list[dict[str, object]]:
    """Probe Windows camera device indexes that CampusGuard can actually open.

    OpenCV does not expose friendly Windows device names, so the UI uses the
    stable device index plus the capture backend that successfully opened it.
    This is useful for virtual cameras such as DroidCam, which may be exposed
    through DirectShow or Media Foundation.
    """
    if max_devices < 1:
        return []

    found: list[dict[str, object]] = []
    seen: set[int] = set()

    for index in range(max_devices):
        for backend_name, backend in (
            ("DirectShow", cv2.CAP_DSHOW),
            ("Media Foundation", cv2.CAP_MSMF),
        ):
            capture = None
            try:
                capture = cv2.VideoCapture(index, backend)
                if not capture.isOpened():
                    continue

                ok, frame = capture.read()
                if not ok or frame is None or frame.size == 0:
                    continue

                height, width = frame.shape[:2]
                found.append(
                    {
                        "index": index,
                        "label": f"Camera {index}  ·  {backend_name}",
                        "backend": backend_name,
                        "resolution": f"{width}x{height}",
                    }
                )
                seen.add(index)
                break
            except Exception:
                continue
            finally:
                if capture is not None:
                    capture.release()

    return found

def _open_capture(source: int | str) -> cv2.VideoCapture:
    """Open a camera and reject backends that open but cannot deliver a frame."""
    def _usable(capture: cv2.VideoCapture) -> bool:
        if capture is None or not capture.isOpened():
            return False
        try:
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except (AttributeError, cv2.error):
            pass

        # A backend can report isOpened()=True while its first read is not
        # actually producing frames (common with some Windows virtual-camera
        # backends). Warm it up before declaring the camera LIVE.
        for _ in range(3):
            ok, frame = capture.read()
            if ok and frame is not None and frame.size:
                return True
            time.sleep(0.08)
        return False

    if isinstance(source, int):
        # Try each Windows backend and keep only one that can really deliver
        # a frame. This prevents a false LIVE state with "Waiting for frames".
        for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
            capture = None
            try:
                capture = cv2.VideoCapture(source, backend)
                if _usable(capture):
                    return capture
            except Exception:
                pass
            finally:
                if capture is not None and not capture.isOpened():
                    capture.release()
            if capture is not None and capture.isOpened():
                capture.release()
        return cv2.VideoCapture()

    capture = cv2.VideoCapture()
    timeout_parameters = [
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
        5000,
        cv2.CAP_PROP_READ_TIMEOUT_MSEC,
        3000,
    ]
    try:
        capture.open(source, cv2.CAP_FFMPEG, timeout_parameters)
    except (TypeError, cv2.error):
        capture.release()
        capture = cv2.VideoCapture(source)

    if capture.isOpened():
        if not _usable(capture):
            capture.release()
            return cv2.VideoCapture()
    return capture


class LatestFrameMailbox:
    """One-slot mailbox; new camera frames replace unprocessed old frames."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._sequence = 0
        self._frame = None
        self._closed = False

    def publish(self, frame) -> None:
        with self._condition:
            if self._closed:
                return
            self._sequence += 1
            self._frame = frame
            self._condition.notify_all()

    def wait_after(self, last_sequence: int, timeout: float = 0.5):
        with self._condition:
            self._condition.wait_for(
                lambda: self._closed or self._sequence > last_sequence,
                timeout=timeout,
            )
            if self._closed:
                return None, None
            if self._sequence <= last_sequence or self._frame is None:
                return None, None
            return self._sequence, self._frame

    @property
    def is_closed(self) -> bool:
        with self._condition:
            return self._closed

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()


class RuntimeOptions:
    def __init__(self, settings: AppSettings, ai_enabled: bool) -> None:
        self._lock = threading.RLock()
        self._settings = settings
        self._ai_enabled = ai_enabled
        self._source_fps = 30.0

    def snapshot(self) -> tuple[AppSettings, bool]:
        with self._lock:
            return self._settings, self._ai_enabled

    def update_settings(self, settings: AppSettings) -> None:
        with self._lock:
            self._settings = settings

    def update_ai_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._ai_enabled = enabled

    def set_source_fps(self, fps: float) -> None:
        with self._lock:
            if fps > 0:
                self._source_fps = float(fps)

    @property
    def source_fps(self) -> float:
        with self._lock:
            return self._source_fps


class CameraCaptureThread(QThread):
    status_changed = Signal(str, str)
    stats_updated = Signal(float, str)

    def __init__(
        self,
        camera: CameraConfig,
        credentials: CameraCredentials,
        mailbox: LatestFrameMailbox,
        options: RuntimeOptions,
    ) -> None:
        super().__init__()
        self.camera = camera
        self.credentials = credentials
        self.mailbox = mailbox
        self.options = options

    def run(self) -> None:
        try:
            source = build_capture_source(
                self.camera.source_type,
                self.camera.source_address,
                self.credentials,
            )
        except ValueError as error:
            self.status_changed.emit("ERROR", str(error))
            self.mailbox.close()
            return

        backoff_seconds = 2
        previously_connected = False
        capture = None
        try:
            while not self.isInterruptionRequested():
                self.status_changed.emit("CONNECTING", "")
                try:
                    capture = _open_capture(source)
                except Exception:
                    capture = None

                if capture is None or not capture.isOpened():
                    if capture is not None:
                        capture.release()
                        capture = None
                    self.status_changed.emit(
                        "OFFLINE",
                        "Camera stream could not be opened. Check the address and credentials.",
                    )
                    settings, _ = self.options.snapshot()
                    if not settings.auto_reconnect:
                        break
                    self._interruptible_sleep(backoff_seconds)
                    backoff_seconds = min(backoff_seconds * 2, 30)
                    continue

                backoff_seconds = 2
                previously_connected = True

                # Use the camera's declared media rate for evidence recording.
                # Some capture backends can be read faster than real time, so
                # using the raw read-loop speed can make saved footage play too fast.
                declared_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
                if 8.0 <= declared_fps <= 60.0:
                    self.options.set_source_fps(declared_fps)
                else:
                    self.options.set_source_fps(30.0)

                frame_count = 0
                stats_started = time.monotonic()
                self.status_changed.emit("LIVE", "")

                consecutive_read_failures = 0
                max_read_failures = 8

                while not self.isInterruptionRequested():
                    ok, frame = capture.read()
                    if not ok or frame is None or frame.size == 0:
                        consecutive_read_failures += 1
                        if consecutive_read_failures < max_read_failures:
                            # Virtual cameras can briefly return an empty frame
                            # while the driver renegotiates without actually
                            # losing the stream.
                            self.msleep(60)
                            continue
                        self.status_changed.emit(
                            "OFFLINE",
                            "Camera stopped returning frames.",
                        )
                        capture.release()
                        capture = None
                        break

                    consecutive_read_failures = 0
                    height, width = frame.shape[:2]
                    self.mailbox.publish(frame)
                    frame_count += 1
                    elapsed = time.monotonic() - stats_started
                    if elapsed >= 1.0:
                        measured_fps = frame_count / elapsed
                        # measured_fps is a diagnostics value only. It must not
                        # become the MP4 playback rate because OpenCV may drain
                        # buffered frames faster than the original camera clock.
                        self.stats_updated.emit(
                            measured_fps,
                            f"{width}x{height}",
                        )
                        frame_count = 0
                        stats_started = time.monotonic()

                if capture is not None:
                    capture.release()
                    capture = None

                if self.isInterruptionRequested():
                    break
                settings, _ = self.options.snapshot()
                if not settings.auto_reconnect:
                    break
                self._interruptible_sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, 30)
        except Exception:
            self.status_changed.emit(
                "ERROR",
                "Camera worker stopped after an unexpected capture error. Verify the source, "
                "credentials, and OpenCV video backend.",
            )
        finally:
            if capture is not None:
                capture.release()
            self.mailbox.close()
            if previously_connected and self.isInterruptionRequested():
                self.status_changed.emit("OFFLINE", "Camera stopped by operator.")

    def _interruptible_sleep(self, seconds: int) -> None:
        remaining_ms = seconds * 1000
        while remaining_ms > 0 and not self.isInterruptionRequested():
            interval = min(remaining_ms, 250)
            self.msleep(interval)
            remaining_ms -= interval


class FrameAnalysisThread(QThread):
    frame_ready = Signal(QImage, str, object)
    model_status = Signal(str, str)
    event_detected = Signal(str, float, str)
    footage_saved = Signal(str)

    def __init__(
        self,
        mailbox: LatestFrameMailbox,
        options: RuntimeOptions,
        footage_dir=None,
    ) -> None:
        super().__init__()
        self.mailbox = mailbox
        self.options = options
        self.footage_recorder = FightFootageRecorder(
            footage_dir or (application_data_dir() / "footage")
        )

    def run(self) -> None:
        latest_sequence = 0
        analysis_frame_index = 0
        last_state = "MODEL NOT LOADED"
        last_confidence = None

        def report_model_status(component: str, message: str) -> None:
            self.model_status.emit(component, message)

        settings, _ = self.options.snapshot()
        try:
            pipeline = VisionPipeline(settings, report_model_status)
        except Exception as error:
            self.model_status.emit("engine", f"AI engine unavailable — {error}")
            pipeline = None

        while not self.isInterruptionRequested():
            sequence, frame = self.mailbox.wait_after(latest_sequence)
            if sequence is None or frame is None:
                if self.mailbox.is_closed:
                    break
                continue
            latest_sequence = sequence
            settings, camera_ai_enabled = self.options.snapshot()

            try:
                analysis_frame_index += 1
                should_analyze = (
                    pipeline is not None
                    and (analysis_frame_index == 1 or analysis_frame_index % 2 == 0)
                )

                if pipeline is None:
                    processed = frame.copy()
                    state = "MODEL NOT LOADED"
                    confidence = None
                    event = None
                elif should_analyze:
                    processed, state, confidence, event = pipeline.process(
                        frame,
                        settings,
                        camera_ai_enabled,
                        settings.tracking_enabled,
                        settings.pose_enabled,
                    )
                    last_state = state
                    last_confidence = confidence
                else:
                    state = last_state
                    confidence = last_confidence
                    event = None
                    processed = pipeline.render_cached(
                        frame,
                        state,
                        confidence,
                    )

                rgb = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB)
                height, width = rgb.shape[:2]
                image = QImage(
                    rgb.data,
                    width,
                    height,
                    int(rgb.strides[0]),
                    QImage.Format.Format_RGB888,
                ).copy()
                self.frame_ready.emit(image, state, confidence)

                finished_footage = self.footage_recorder.update(
                    frame,
                    state,
                    event_started=event is not None,
                    source_fps=self.options.source_fps,
                )
                if finished_footage is not None:
                    self.footage_saved.emit(str(finished_footage))

                if event is not None:
                    event_name, event_confidence, severity = event
                    self.event_detected.emit(event_name, event_confidence, severity)
            except Exception as error:
                self.model_status.emit("engine", f"Frame analysis error — {error}")

        finished_footage = self.footage_recorder.stop()
        if finished_footage is not None:
            self.footage_saved.emit(str(finished_footage))


class CameraTestThread(QThread):
    result_ready = Signal(bool, str)

    def __init__(
        self,
        source_type: str,
        source_address: str,
        credentials: CameraCredentials,
    ) -> None:
        super().__init__()
        self.source_type = source_type
        self.source_address = source_address
        self.credentials = credentials

    def run(self) -> None:
        capture = None
        try:
            source = build_capture_source(
                self.source_type,
                self.source_address,
                self.credentials,
            )
            capture = _open_capture(source)
            if capture is None or not capture.isOpened():
                self.result_ready.emit(
                    False,
                    "Connection failed. Check the source address and camera credentials.",
                )
                return
            ok, frame = capture.read()
            if not ok or frame is None or frame.size == 0:
                self.result_ready.emit(False, "Connected, but the source returned no frame.")
                return
            height, width = frame.shape[:2]
            self.result_ready.emit(True, f"Connection successful — {width}x{height}")
        except Exception:
            self.result_ready.emit(
                False,
                "Connection test encountered an error. Check the source, credentials, and video backend.",
            )
        finally:
            if capture is not None:
                capture.release()


class LocalVideoTestThread(QThread):
    """Play one local video through the production AI pipeline and expose events."""

    frame_ready = Signal(QImage, str, object)
    status_changed = Signal(str)
    model_status = Signal(str, str)
    event_detected = Signal(str, float, str)
    footage_saved = Signal(str)

    def __init__(self, video_path: str, settings: AppSettings) -> None:
        super().__init__()
        self.video_path = video_path
        self.settings = settings
        self.footage_recorder = FightFootageRecorder(
            application_data_dir() / "footage"
        )

    def run(self) -> None:
        capture = None
        try:
            capture = cv2.VideoCapture(self.video_path)
            if capture is None or not capture.isOpened():
                self.status_changed.emit("ERROR — Could not open the selected video.")
                return

            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            if fps <= 1.0 or fps > 240.0:
                fps = 30.0
            frame_interval = 1.0 / fps
            next_frame_time = time.monotonic()

            # A local test always exercises the AI pipeline, while keeping the
            # user's other production settings unchanged.
            test_settings = AppSettings.from_dict(
                {
                    **self.settings.to_dict(),
                    "detection_enabled": True,
                }
            )

            def report_model_status(component: str, message: str) -> None:
                self.model_status.emit(component, message)

            self.status_changed.emit("LOADING MODEL")
            pipeline = VisionPipeline(test_settings, report_model_status)

            self.status_changed.emit("PLAYING")
            while not self.isInterruptionRequested():
                ok, frame = capture.read()
                if not ok or frame is None or frame.size == 0:
                    break

                processed, state, confidence, event = pipeline.process(
                    frame,
                    test_settings,
                    True,
                    test_settings.tracking_enabled,
                    test_settings.pose_enabled,
                )

                rgb = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB)
                height, width = rgb.shape[:2]
                image = QImage(
                    rgb.data,
                    width,
                    height,
                    int(rgb.strides[0]),
                    QImage.Format.Format_RGB888,
                ).copy()
                self.frame_ready.emit(image, state, confidence)

                finished_footage = self.footage_recorder.update(
                    frame,
                    state,
                    event_started=event is not None,
                    source_fps=fps,
                )
                if finished_footage is not None:
                    self.footage_saved.emit(str(finished_footage))

                if event is not None:
                    event_name, event_confidence, severity = event
                    self.event_detected.emit(event_name, event_confidence, severity)

                next_frame_time += frame_interval
                delay = next_frame_time - time.monotonic()
                if delay > 0:
                    self.msleep(max(1, int(delay * 1000)))
                elif delay < -frame_interval * 4:
                    next_frame_time = time.monotonic()

            if self.isInterruptionRequested():
                self.status_changed.emit("STOPPED")
            else:
                self.status_changed.emit("FINISHED")
        except Exception as error:
            self.status_changed.emit(f"ERROR — {error}")
        finally:
            finished_footage = self.footage_recorder.stop()
            if finished_footage is not None:
                self.footage_saved.emit(str(finished_footage))
            if capture is not None:
                capture.release()


@dataclass
class CameraSession:
    camera: CameraConfig
    mailbox: LatestFrameMailbox
    options: RuntimeOptions
    capture_thread: CameraCaptureThread
    analysis_thread: FrameAnalysisThread

    def stop(self) -> None:
        self.mailbox.close()
        self.capture_thread.requestInterruption()
        self.analysis_thread.requestInterruption()


class CameraManager(QObject):
    camera_status_changed = Signal(str, str, str)
    camera_stats_changed = Signal(str, float, str)
    frame_ready = Signal(str, QImage, str, object)
    model_status_changed = Signal(str, str, str)
    event_detected = Signal(str, str, float, str)
    footage_saved = Signal(str, str)

    def __init__(
        self,
        vault: CredentialVault,
        footage_dir=None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.vault = vault
        self.footage_dir = footage_dir
        self._sessions: dict[str, CameraSession] = {}
        self._retiring: list[CameraSession] = []
        self._settings = AppSettings()
        self._purge_timer = QTimer(self)
        self._purge_timer.setInterval(1000)
        self._purge_timer.timeout.connect(self._purge_finished_sessions)
        self._purge_timer.start()

    def start_camera(self, camera: CameraConfig) -> None:
        self.stop_camera(camera.camera_id)
        try:
            credentials = self.vault.load(camera.camera_id)
        except Exception:
            self.camera_status_changed.emit(
                camera.camera_id,
                "ERROR",
                "Could not read this camera's credentials from the operating-system credential vault.",
            )
            return
        mailbox = LatestFrameMailbox()
        options = RuntimeOptions(self._settings, camera.ai_enabled)
        capture = CameraCaptureThread(camera, credentials, mailbox, options)
        analysis = FrameAnalysisThread(mailbox, options, self.footage_dir)

        capture.status_changed.connect(
            lambda status, message, camera_id=camera.camera_id:
            self.camera_status_changed.emit(camera_id, status, message)
        )
        capture.stats_updated.connect(
            lambda fps, resolution, camera_id=camera.camera_id:
            self.camera_stats_changed.emit(camera_id, fps, resolution)
        )
        analysis.frame_ready.connect(
            lambda image, state, confidence, camera_id=camera.camera_id:
            self.frame_ready.emit(camera_id, image, state, confidence)
        )
        analysis.model_status.connect(
            lambda component, message, camera_id=camera.camera_id:
            self.model_status_changed.emit(camera_id, component, message)
        )
        analysis.event_detected.connect(
            lambda event, confidence, severity, camera_id=camera.camera_id:
            self.event_detected.emit(camera_id, event, confidence, severity)
        )
        analysis.footage_saved.connect(
            lambda path, camera_id=camera.camera_id:
            self.footage_saved.emit(camera_id, path)
        )

        session = CameraSession(camera, mailbox, options, capture, analysis)
        self._sessions[camera.camera_id] = session
        analysis.start()
        capture.start()

    def stop_camera(self, camera_id: str) -> None:
        session = self._sessions.pop(camera_id, None)
        if session is None:
            return
        session.stop()
        self._retiring.append(session)

    def set_settings(self, settings: AppSettings) -> None:
        self._settings = settings
        for session in self._sessions.values():
            session.options.update_settings(settings)

    def set_camera_ai(self, camera_id: str, enabled: bool) -> None:
        session = self._sessions.get(camera_id)
        if session is not None:
            session.options.update_ai_enabled(enabled)

    def reconnect(self, camera_id: str, camera: CameraConfig | None = None) -> None:
        session = self._sessions.get(camera_id)
        if session is None:
            if camera is not None:
                self.start_camera(camera)
            return
        session.stop()
        self._retiring.append(session)
        self._sessions.pop(camera_id, None)
        if camera is not None:
            QTimer.singleShot(
                100,
                lambda: self._start_after_stop(camera, session),
            )

    def stop_all(self, timeout_ms: int = 5000) -> None:
        sessions = list(self._sessions.values()) + self._retiring
        self._sessions.clear()
        self._retiring.clear()
        for session in sessions:
            session.stop()
        for session in sessions:
            if not session.capture_thread.wait(timeout_ms):
                session.capture_thread.wait()
            if not session.analysis_thread.wait(timeout_ms):
                session.analysis_thread.wait()

    def _purge_finished_sessions(self) -> None:
        self._retiring = [
            session
            for session in self._retiring
            if session.capture_thread.isRunning() or session.analysis_thread.isRunning()
        ]

    def _start_after_stop(
        self,
        camera: CameraConfig,
        previous_session: CameraSession,
    ) -> None:
        if (
            previous_session.capture_thread.isRunning()
            or previous_session.analysis_thread.isRunning()
        ):
            QTimer.singleShot(
                250,
                lambda: self._start_after_stop(camera, previous_session),
            )
            return
        self.start_camera(camera)