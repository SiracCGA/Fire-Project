import sys
import math
import time
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QThread, Signal, Slot
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QBrush, QPainterPath
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QLineEdit,
    QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QTextEdit,
    QSizePolicy, QProgressBar
)

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import psutil
except ImportError:
    psutil = None


BG = "#1d293f"
PANEL = "#24324d"
DARK = "#050811"
INNER = "#101724"
ORANGE = "#ff9800"
TEXT = "#b0bec5"
MUTED = "#90a4ae"
GREEN = "#00e676"
RED = "#ff1744"
CYAN = "#00e5ff"

VIDEO_URL = "http://127.0.0.1:5000/video"
DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


class Panel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")


class RingGauge(QWidget):
    def __init__(self, title, value=0, parent=None):
        super().__init__(parent)
        self.title = title
        self.value = value
        self.setFixedSize(94, 112)

    def setValue(self, value):
        self.value = max(0, min(100, int(value)))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QColor(MUTED))
        p.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        p.drawText(0, 0, self.width(), 18, Qt.AlignmentFlag.AlignHCenter, self.title)
        x, y, size = 8, 22, 76
        p.setPen(QPen(QColor(INNER), 7))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(x, y, size, size, 90 * 16, -360 * 16)
        p.setPen(QPen(QColor(ORANGE), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        p.drawArc(x, y, size, size, 90 * 16, -int(360 * self.value / 100) * 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#162032"))
        p.drawEllipse(x + 8, y + 8, size - 16, size - 16)
        p.setPen(QColor("white"))
        p.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        p.drawText(x, y, size, size, Qt.AlignmentFlag.AlignCenter, f"{self.value}%")


class CameraWorker(QThread):
    frameReady = Signal(QImage, float)
    connectionChanged = Signal(bool, str)

    def __init__(self, url=VIDEO_URL, parent=None):
        super().__init__(parent)
        self.url = url
        self._running = True

    def stop(self):
        self._running = False
        self.wait(2000)

    def run(self):
        if cv2 is None:
            self.connectionChanged.emit(False, "OpenCV kurulu değil (pip install opencv-python)")
            return

        while self._running:
            cap = cv2.VideoCapture(self.url)
            if not cap.isOpened():
                self.connectionChanged.emit(False, f"Kamera bağlantısı bekleniyor: {self.url}")
                cap.release()
                self.msleep(1200)
                continue

            self.connectionChanged.emit(True, "Kamera akışı bağlandı.")
            last_time = time.perf_counter()
            fps = 0.0

            while self._running:
                ok, frame = cap.read()
                if not ok:
                    self.connectionChanged.emit(False, "Kamera akışı kesildi, yeniden bağlanılıyor...")
                    break

                now = time.perf_counter()
                elapsed = now - last_time
                last_time = now
                if elapsed > 0:
                    instant_fps = 1.0 / elapsed
                    fps = instant_fps if fps == 0 else (fps * 0.85 + instant_fps * 0.15)

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                qimage = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
                self.frameReady.emit(qimage, fps)

            cap.release()
            if self._running:
                self.msleep(700)


class CameraView(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._image = QImage()
        self.fps = 0.0
        self.setFixedSize(640, 480)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setObjectName("cameraView")
        self.setText("KAMERA VERİSİ BEKLENİYOR...")
        self.setStyleSheet(
            "QLabel#cameraView { background:#050811; border:1px solid #37474f;"
            " border-radius:4px; color:#546e7a; font:12px Consolas; }"
        )

    @Slot(QImage, float)
    def setFrame(self, image, fps):
        self._image = image
        self.fps = fps
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if not self._image.isNull():
            scaled = self._image.scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            p.drawImage(x, y, scaled)
        else:
            p.setPen(QColor("#546e7a"))
            p.setFont(QFont("Consolas", 10))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "KAMERA VERİSİ BEKLENİYOR...")

        # FPS badge and camera label
        p.setPen(QPen(QColor("#805b2b"), 1))
        p.setBrush(QColor(16, 23, 36, 220))
        p.drawRoundedRect(self.width() - 88, self.height() - 43, 76, 19, 5, 5)
        p.setPen(QColor(ORANGE))
        p.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        p.drawText(self.width() - 83, self.height() - 29, f"FPS: {self.fps:.1f}")
        p.setPen(QColor("#4f6a85"))
        p.drawText(self.width() - 63, self.height() - 8, "CAM-01")


class RadarWidget(QWidget):
    """Eight-sector proximity radar. Activate sectors with setSector()."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.active = {direction: False for direction in DIRECTIONS}
        self.setMinimumSize(250, 250)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def setSector(self, direction, detected=True):
        direction = direction.upper()
        if direction not in self.active:
            raise ValueError(f"Direction must be one of: {', '.join(DIRECTIONS)}")
        self.active[direction] = bool(detected)
        self.update()

    def setDetections(self, directions):
        active = {str(d).upper() for d in directions}
        unknown = active.difference(DIRECTIONS)
        if unknown:
            raise ValueError(f"Unknown radar direction(s): {', '.join(sorted(unknown))}")
        self.active = {direction: direction in active for direction in DIRECTIONS}
        self.update()

    def clear(self):
        self.setDetections([])

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        side = min(self.width(), self.height()) - 52
        radius = side / 2
        cx, cy = self.width() / 2, self.height() / 2
        if radius < 35:
            return

        # Eight equal sectors. North is at the top; each sector is 45 degrees.
        for i, direction in enumerate(DIRECTIONS):
            center_angle = -90 + i * 45
            start_angle = center_angle - 22.5
            path = QPainterPath()
            path.moveTo(cx, cy)
            steps = 12
            for step in range(steps + 1):
                angle = math.radians(start_angle + 45 * step / steps)
                point = (cx + radius * math.cos(angle), cy + radius * math.sin(angle))
                if step == 0:
                    path.lineTo(*point)
                else:
                    path.lineTo(*point)
            path.closeSubpath()

            if self.active[direction]:
                fill = QColor(255, 23, 68, 190)
                edge = QColor(RED)
            else:
                fill = QColor("#17243a")
                edge = QColor("#52657c")

            p.setPen(QPen(edge, 1.4))
            p.setBrush(QBrush(fill))
            p.drawPath(path)

        # Radar rings and crosshair
        p.setBrush(Qt.BrushStyle.NoBrush)
        for fraction in (0.33, 0.66, 1.0):
            r = radius * fraction
            p.setPen(QPen(QColor("#52657c"), 1, Qt.PenStyle.DotLine))
            p.drawEllipse(int(cx-r), int(cy-r), int(2*r), int(2*r))
        p.setPen(QPen(QColor("#52657c"), 1, Qt.PenStyle.DotLine))
        p.drawLine(int(cx-radius), int(cy), int(cx+radius), int(cy))
        p.drawLine(int(cx), int(cy-radius), int(cx), int(cy+radius))

        # Center hub
        p.setPen(QPen(QColor("#0b1424"), 2))
        p.setBrush(QColor("#101b2e"))
        p.drawEllipse(int(cx-31), int(cy-31), 62, 62)
        p.setPen(QColor(MUTED))
        p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        p.drawText(int(cx-29), int(cy-10), 58, 20, Qt.AlignmentFlag.AlignCenter, "MERKEZ")
        p.setPen(QColor(ORANGE))
        p.setFont(QFont("Consolas", 7))
        p.drawText(int(cx-29), int(cy+7), 58, 14, Qt.AlignmentFlag.AlignCenter, "RADAR")

        # Direction labels outside the radar
        label_radius = radius + 17
        p.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        for i, direction in enumerate(DIRECTIONS):
            angle = math.radians(-90 + i * 45)
            x = cx + label_radius * math.cos(angle)
            y = cy + label_radius * math.sin(angle)
            p.setPen(QColor(RED if self.active[direction] else MUTED))
            p.drawText(int(x-15), int(y-8), 30, 16, Qt.AlignmentFlag.AlignCenter, direction)


class FireSuppressionWindow(QMainWindow):
    movementRequested = Signal(str)
    connectRequested = Signal(str)
    terminalCommand = Signal(str)
    radarSectorChanged = Signal(str, bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Otonom Yangın Söndürme Sistemi")
        self.resize(1724, 900)
        self.setMinimumSize(1180, 720)
        self.camera_worker = None
        self._build_ui()
        self._apply_style()
        self._connect_signals()
        self._start_stats_timer()
        self.add_log("Sistem başarıyla başlatıldı.", "info")
        self.alarm_output.append(
            "> [ÖRNEK] ALEV ALGILANDI: Kamera | Güven: %94\n"
            "> [ÖRNEK] IR-2: Isı kaynağı algılandı\n"
            "> [ÖRNEK] DUMAN ALGILANDI: Yoğunluk orta\n"
            "> [ÖRNEK] Sıcaklık uyarısı: 68.5 °C\n"
            "> [ÖRNEK] Radar: Kuzeydoğu yönünde hareket"
        )
        self.setAlarm(True)
        self.start_camera()

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(12, 4, 12, 2)
        title = QLabel("Otonom Yangın Söndürme Sistemi")
        title.setStyleSheet("color:white; font-size:26px; font-weight:800;")
        header.addWidget(title)
        header.addStretch()
        root.addLayout(header)

        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(12)
        root.addLayout(columns, 1)

        # Left: logs, connection state, CPU/RAM and terminal
        left = QWidget()
        left.setFixedWidth(372)
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(12)
        columns.addWidget(left)

        log_panel = Panel()
        log_panel.setMinimumHeight(185)
        log_l = QVBoxLayout(log_panel)
        log_l.setContentsMargins(9, 9, 9, 9)
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setObjectName("logs")
        log_l.addWidget(self.logs)
        left_l.addWidget(log_panel)

        connection_panel = Panel()
        connection_panel.setFixedHeight(64)
        conn_l = QHBoxLayout(connection_panel)
        conn_l.setContentsMargins(12, 8, 12, 8)
        conn_l.setSpacing(8)
        conn_l.addWidget(QLabel("EK-BİRİM BAĞLANTISI"))
        self.connection_status = QLabel("BAĞLI DEĞİL")
        self.connection_status.setObjectName("connectionStatus")
        conn_l.addWidget(self.connection_status, 1)
        left_l.addWidget(connection_panel)

        stats_panel = Panel()
        stats_panel.setFixedHeight(126)
        stats_l = QHBoxLayout(stats_panel)
        stats_l.setContentsMargins(35, 8, 35, 8)
        stats_l.setSpacing(20)
        self.cpu_gauge = RingGauge("CPU", 0)
        self.ram_gauge = RingGauge("RAM", 0)
        stats_l.addStretch()
        stats_l.addWidget(self.cpu_gauge)
        stats_l.addWidget(self.ram_gauge)
        stats_l.addStretch()
        left_l.addWidget(stats_panel)

        terminal_panel = Panel()
        terminal_l = QVBoxLayout(terminal_panel)
        terminal_l.setContentsMargins(9, 9, 9, 9)
        self.terminal_output = QTextEdit()
        self.terminal_output.setReadOnly(True)
        self.terminal_output.setObjectName("terminalOutput")
        terminal_l.addWidget(self.terminal_output, 1)
        terminal_row = QHBoxLayout()
        prompt = QLabel("sh~:")
        prompt.setObjectName("prompt")
        self.terminal_input = QLineEdit()
        self.terminal_input.setObjectName("terminalInput")
        terminal_row.addWidget(prompt)
        terminal_row.addWidget(self.terminal_input, 1)
        terminal_l.addLayout(terminal_row)
        left_l.addWidget(terminal_panel, 1)

        # Center: one live camera and radar panel
        center = QWidget()
        center_l = QVBoxLayout(center)
        center_l.setContentsMargins(0, 0, 0, 0)
        center_l.setSpacing(12)
        columns.addWidget(center, 1)

        video_panel = Panel()
        video_l = QVBoxLayout(video_panel)
        video_l.setContentsMargins(16, 16, 16, 16)
        self.camera = CameraView()
        video_l.addWidget(self.camera)
        center_l.addWidget(video_panel, 1)

        radar_panel = Panel()
        radar_l = QVBoxLayout(radar_panel)
        radar_l.setContentsMargins(12, 8, 12, 8)
        radar_title = QLabel("ÇEVRESEL ALGILAMA RADARI")
        radar_title.setObjectName("sectionTitle")
        radar_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        radar_l.addWidget(radar_title)
        self.radar = RadarWidget()
        radar_l.addWidget(self.radar, 1)
        center_l.addWidget(radar_panel, 1)

        # Right: four IR sensors and alarms
        right = QWidget()
        right.setFixedWidth(372)
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(12)
        columns.addWidget(right)

        ir_panel = Panel()
        ir_l = QGridLayout(ir_panel)
        ir_l.setContentsMargins(12, 12, 12, 12)
        ir_l.setHorizontalSpacing(12)
        ir_l.setVerticalSpacing(12)
        self.ir_leds = []
        for i in range(4):
            box = QFrame()
            box.setObjectName("irBox")
            box_l = QVBoxLayout(box)
            box_l.setContentsMargins(6, 8, 6, 8)
            label = QLabel(f"IR {i+1}")
            label.setObjectName("climateLabel")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            led = QLabel("●")
            led.setObjectName("irLed")
            led.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box_l.addWidget(label)
            box_l.addWidget(led)
            ir_l.addWidget(box, i // 2, i % 2)
            self.ir_leds.append(led)
        right_l.addWidget(ir_panel)

        alarm_panel = Panel()
        alarm_l = QVBoxLayout(alarm_panel)
        alarm_l.setContentsMargins(12, 10, 12, 10)
        alarm_l.setSpacing(8)
        alarm_header = QLabel("ALGILANAN VERİLER & İHBARLAR")
        alarm_header.setObjectName("sectionTitle")
        alarm_l.addWidget(alarm_header)
        self.alarm_output = QTextEdit()
        self.alarm_output.setReadOnly(True)
        self.alarm_output.setObjectName("alarmOutput")
        alarm_l.addWidget(self.alarm_output, 1)
        alarm_footer = QHBoxLayout()
        alarm_title = QLabel("ALARM:")
        alarm_title.setStyleSheet("color:white; font-weight:bold;")
        self.alarm_led = QLabel("●")
        self.alarm_led.setObjectName("alarmLed")
        alarm_footer.addWidget(alarm_title)
        alarm_footer.addWidget(self.alarm_led)
        alarm_footer.addStretch()
        alarm_l.addLayout(alarm_footer)
        right_l.addWidget(alarm_panel, 1)

    def _apply_style(self):
        self.setStyleSheet(f"""
            QWidget#central {{ background:{BG}; color:{TEXT}; font-family:'Segoe UI'; }}
            QFrame#panel {{ background:{PANEL}; border:2px solid {ORANGE}; border-radius:19px; }}
            QLabel {{ color:{TEXT}; }}
            QTextEdit {{ border:0; background:transparent; color:#7cd6ff; font:10px Consolas; }}
            QLineEdit#terminalInput {{ background:{DARK}; border:1px solid #26364b;
                border-radius:3px; padding:5px; color:#00ff66; font:13px Consolas; }}
            QLabel#connectionStatus {{ color:{ORANGE}; font:bold 12px Consolas; }}
            QLabel#sectionTitle, QLabel#climateLabel {{ color:{MUTED}; font:bold 11px Consolas; }}
            QFrame#irBox {{ background:transparent; border:1px solid #37474f; border-radius:6px; }}
            QLabel#irLed {{ color:#37474f; font-size:30px; }}
            QTextEdit#alarmOutput {{ background:{DARK}; border:1px solid #37474f; border-radius:4px;
                padding:6px; color:{RED}; font:bold 11px Consolas; }}
            QTextEdit#terminalOutput {{ background:{DARK}; color:#00ff66; font:12px Consolas; }}
            QLabel#prompt {{ color:#00ff66; font:bold 13px Consolas; }}
            QLabel#alarmLed {{ color:#546e7a; font-size:17px; }}
        """)

    def _connect_signals(self):
        self.terminal_input.returnPressed.connect(self._run_terminal_command)

    def _start_stats_timer(self):
        self.stats_timer = QTimer(self)
        self.stats_timer.timeout.connect(self._refresh_system_stats)
        self.stats_timer.start(1500)
        self._refresh_system_stats()

    def _refresh_system_stats(self):
        if psutil:
            self.cpu_gauge.setValue(psutil.cpu_percent())
            self.ram_gauge.setValue(psutil.virtual_memory().percent)

    def start_camera(self):
        """Connect to the MJPEG endpoint at http://127.0.0.1:5000/video."""
        if cv2 is None:
            self.add_log("OpenCV bulunamadı. 'pip install opencv-python' çalıştırın.", "error")
            return
        if self.camera_worker and self.camera_worker.isRunning():
            return
        self.camera_worker = CameraWorker(VIDEO_URL, self)
        self.camera_worker.frameReady.connect(self.camera.setFrame)
        self.camera_worker.connectionChanged.connect(self._camera_status)
        self.camera_worker.start()
        self.add_log(f"Kamera akışına bağlanılıyor: {VIDEO_URL}", "info")

    @Slot(bool, str)
    def _camera_status(self, connected, message):
        self.add_log(message, "info" if connected else "warning")

    def setConnectionStatus(self, connected):
        """Call this when your robot communication layer connects/disconnects."""
        self.connection_status.setText("BAĞLANILDI" if connected else "BAĞLI DEĞİL")
        self.connection_status.setStyleSheet(
            f"color:{GREEN if connected else ORANGE}; font:bold 12px Consolas;"
        )
        self.add_log("Ek-birim bağlantısı kuruldu." if connected else "Ek-birim bağlantısı kesildi.",
                     "info" if connected else "error")

    def setIR(self, sensor_index, active):
        """sensor_index: 0..3"""
        if sensor_index not in range(4):
            raise ValueError("IR sensor index must be 0, 1, 2 or 3.")
        self.ir_leds[sensor_index].setStyleSheet(
            f"color:{RED if active else '#37474f'}; font-size:30px;"
        )

    def setRadarSector(self, direction, detected=True):
        """direction: N, NE, E, SE, S, SW, W or NW"""
        self.radar.setSector(direction, detected)
        self.radarSectorChanged.emit(direction.upper(), bool(detected))

    def setRadarDetections(self, directions):
        """Example: window.setRadarDetections(['N', 'SW'])"""
        self.radar.setDetections(directions)

    def clearRadar(self):
        self.radar.clear()

    def add_log(self, message, level="info"):
        colors = {"info": "#7cd6ff", "warning": "#ffe082", "error": "#ff8a8a"}
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append(
            f"<span style='color:{colors.get(level, colors['info'])}'>"
            f"[{timestamp}] {message}</span>"
        )

    def add_alarm(self, message):
        self.alarm_output.append(f"> {message}")
        self.setAlarm(True)

    def setAlarm(self, active):
        self.alarm_led.setStyleSheet(
            f"color:{RED if active else '#546e7a'}; font-size:17px;"
        )

    def _run_terminal_command(self):
        command = self.terminal_input.text().strip()
        if not command:
            return
        self.terminal_input.clear()
        self.terminal_output.append(f"<span style='color:#00ff66'>sh~: {command}</span>")
        self.terminalCommand.emit(command)
        cmd = command.lower()
        if cmd == "clear":
            self.terminal_output.clear()
        elif cmd == "help":
            self.terminal_output.append("Mevcut komutlar: help, clear, status")
        elif cmd == "status":
            self.terminal_output.append(
                "Kamera: " + ("bağlı" if self.camera_worker and self.camera_worker.isRunning()
                              else "bağlantı bekleniyor")
            )
        else:
            self.terminal_output.append(f"'{command}' komutu bulunamadı.")

    def closeEvent(self, event):
        if self.camera_worker and self.camera_worker.isRunning():
            self.camera_worker.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    window = FireSuppressionWindow()

    # Example: simulated robot link state. Replace with your real connection callback.
    # window.setConnectionStatus(True)
    #
    # Example radar updates:
    # window.setRadarDetections(["N", "SE"])
    # window.setRadarSector("W", True)
    #
    # Example four IR sensors:
    # window.setIR(0, True)
    # window.setIR(1, False)
    # window.setIR(2, True)
    # window.setIR(3, False)

    window.show()
    sys.exit(app.exec())