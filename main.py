import json
import logging
import random
import sys
from datetime import date, datetime
from pathlib import Path

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QTimer, Qt, QUrl
from PyQt6.QtGui import QAction, QFont, QIcon, QMovie
from PyQt6.QtMultimedia import QSoundEffect
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton,
    QSystemTrayIcon, QVBoxLayout, QWidget
)

BASE_DIR = Path(__file__).resolve().parent
ASSET_DIR = BASE_DIR / 'assets'
DATA_DIR = BASE_DIR / 'data'
LOG_DIR = BASE_DIR / 'logs'
SOUND_DIR = BASE_DIR / 'sounds'
CONFIG_FILE = BASE_DIR / 'config.json'
DATA_FILE = DATA_DIR / 'streak.json'

for folder in (DATA_DIR, LOG_DIR, SOUND_DIR):
    folder.mkdir(exist_ok=True)

logging.basicConfig(
    filename=LOG_DIR / 'app.log',
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)

DEFAULT_CONFIG = {
    'reminder_minutes': 60,
    'snooze_minutes': 10,
    'daily_goal': 8,
    'show_on_startup': True,
    'startup_delay_seconds': 3,
    'character_width': 260,
    'character_height': 260,
    'screen_margin_right': 24,
    'screen_margin_bottom': 44,
    'walk_duration_ms': 2600,
    'response_display_ms': 4500,
    'sound_enabled': True,
    'asset_names': {
        'walk_out':'walk out.gif',
        'walk_in': 'walk in.gif',
        'reminder': 'reminder mode.gif',
        'happy': 'happy mode.gif',
        'sad': 'sad mode.gif',
        'legend': 'hydration legend mode.gif'
    }
}


def load_json(path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        logging.exception('Could not read %s', path)
    return default.copy()


def save_json(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temp.replace(path)


class WaterBuddy(QWidget):
    def __init__(self):
        super().__init__()
        self.config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
        self.data = load_json(DATA_FILE, self.default_data())
        self.ensure_today()
        self.movie = None
        self.animation = None
        self.snooze_timer = None
        self.sound = QSoundEffect(self)
        self.build_ui()
        self.build_tray()
        self.schedule_timer = QTimer(self)
        self.schedule_timer.timeout.connect(self.show_reminder)
        self.schedule_timer.start(int(self.config['reminder_minutes'] * 60_000))
        self.hide()
        if self.config.get('show_on_startup', True):
            QTimer.singleShot(int(self.config.get('startup_delay_seconds', 3) * 1000), self.show_reminder)

    @staticmethod
    def default_data():
        return {'date': date.today().isoformat(), 'water_count': 0, 'daily_goal': 8,
                'last_confirmed': None, 'reminders_shown': 0, 'snoozes': 0}

    def ensure_today(self):
        today = date.today().isoformat()
        if self.data.get('date') != today:
            self.data = self.default_data()
        self.data['daily_goal'] = int(self.config.get('daily_goal', 8))
        save_json(DATA_FILE, self.data)

    def build_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(390, 430)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        self.bubble = QFrame()
        self.bubble.setObjectName('bubble')
        bubble_layout = QVBoxLayout(self.bubble)
        bubble_layout.setContentsMargins(16, 12, 16, 12)
        bubble_layout.setSpacing(8)

        self.message = QLabel('U had water? 💧')
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setFont(QFont('Segoe UI', 13, QFont.Weight.DemiBold))
        bubble_layout.addWidget(self.message)

        self.counter = QLabel('')
        self.counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.counter.setFont(QFont('Segoe UI', 9))
        bubble_layout.addWidget(self.counter)

        buttons = QHBoxLayout()
        self.yes_btn = QPushButton('👍')
        self.later_btn = QPushButton('⏰')
        self.no_btn = QPushButton('🤫')
        self.yes_btn.clicked.connect(self.drank_water)
        self.later_btn.clicked.connect(self.snooze)
        self.no_btn.clicked.connect(self.no_water)
        for button in (self.yes_btn, self.later_btn, self.no_btn):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.addWidget(button)
        bubble_layout.addLayout(buttons)
        outer.addWidget(self.bubble)

        self.character = QLabel()
        self.character.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.character.setFixedSize(
            int(self.config['character_width']),
            int(self.config['character_height'])
        )
        outer.addWidget(self.character, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.setStyleSheet('''
            QFrame#bubble {
                background: rgba(248, 251, 255, 245);
                border: 2px solid #82b8ff;
                border-radius: 18px;
            }
            QLabel { color: #14213d; background: transparent; }
            QPushButton {
                background: #dcecff; color: #14213d; border: 1px solid #8ab9f2;
                border-radius: 10px; padding: 7px 10px; font: 600 10pt "Segoe UI";
            }
            QPushButton:hover { background: #bcdcff; }
            QPushButton:pressed { background: #93c5fd; }
        ''')

    def build_tray(self):
        icon_path = ASSET_DIR / 'icon.png'
        icon = QIcon(str(icon_path)) if icon_path.exists() else QApplication.style().standardIcon(
            QApplication.style().StandardPixmap.SP_MessageBoxInformation
        )
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip('Water Buddy')
        menu = QMenu()
        show_action = QAction('Hydration check now', self)
        show_action.triggered.connect(self.show_reminder)
        stats_action = QAction('Today’s progress', self)
        stats_action.triggered.connect(self.show_progress)
        reset_action = QAction('Reset today', self)
        reset_action.triggered.connect(self.reset_today)
        quit_action = QAction('Quit Water Buddy', self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(show_action)
        menu.addAction(stats_action)
        menu.addAction(reset_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_reminder()

    def asset_path(self, mode):
        return ASSET_DIR / self.config['asset_names'][mode]

    def set_mode(self, mode):
        path = self.asset_path(mode)
        if not path.exists():
            self.character.setText(f'Missing animation:\n{path.name}')
            logging.error('Missing asset: %s', path)
            return False
        if self.movie:
            self.movie.stop()
            self.movie.deleteLater()
        self.movie = QMovie(str(path))
        self.movie.setScaledSize(self.character.size())
        self.character.setMovie(self.movie)
        self.movie.start()
        return True

    def set_buttons_visible(self, visible):
        for button in (self.yes_btn, self.later_btn, self.no_btn):
            button.setVisible(visible)

    def target_position(self):
        screen = QApplication.screenAt(QApplication.primaryScreen().availableGeometry().center())
        geometry = screen.availableGeometry()
        x = geometry.left() + 30

        y = (
            geometry.bottom()
            - self.height()
            - 44
        )

        return QPoint(max(geometry.left(), x), max(geometry.top(), y)), geometry

    def show_reminder(self):
        self.ensure_today()
        self.data['reminders_shown'] = int(self.data.get('reminders_shown', 0)) + 1
        save_json(DATA_FILE, self.data)
        lines = [
    "...Hydrate.",
    "Water. Now.",
    "You're dehydrated, aren't you?",
    "Go drink water. I'll wait.",
    "Your water bottle misses you.",
    "You remembered everything except water?",
    "Just take a sip.",
    "Hydration seems necessary.",
    "Drink water",
    "You look like you need a glass of water.",
    "A sip wouldn't hurt.",
    "Water first.",
    "Water break.",
    "Don't make me remind you again.",
    "You know what this is about. 💧",
    "Hydrate before you become a raisin.",
    "Consider drinking water.",
    "Your survival stats would improve.",
    "I brought water. The rest is on you.",
    "Hydration is not optional.",
    "Just one glass.",
    "Get up. Grab water. Return.",
    "Drink water. That's the mission.",
    "Focus later. Hydrate now.",
    "You can handle one sip.",
    "Seriously. Water."
]
        self.message.setText(random.choice(lines))
        self.update_counter()
        self.set_buttons_visible(True)
        self.bubble.show()
        self.set_mode('walk_in')
        target, geometry = self.target_position()

        start = QPoint(
            -self.width(),
            target.y()
        )
        self.move(start)
        self.show()
        self.raise_()
        self.play_sound()
        self.animation = QPropertyAnimation(self, b'pos')
        self.animation.setDuration(int(self.config['walk_duration_ms']))
        self.animation.setStartValue(start)
        self.animation.setEndValue(target)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.finished.connect(lambda: self.set_mode('reminder'))
        self.animation.start()
        logging.info('Reminder shown')

    def update_counter(self):
        count = int(self.data.get('water_count', 0))
        goal = int(self.config.get('daily_goal', 8))
        self.counter.setText(f'Today: {count}/{goal} glasses')

    def drank_water(self):
        self.ensure_today()
        self.data['water_count'] = int(self.data.get('water_count', 0)) + 1
        self.data['last_confirmed'] = datetime.now().isoformat(timespec='seconds')
        save_json(DATA_FILE, self.data)
        self.set_buttons_visible(False)
        self.update_counter()
        if self.data['water_count'] >= int(self.config['daily_goal']):
            self.set_mode('legend')
            self.message.setText('WATER LEGEND! 🏆💧')
        else:
            self.set_mode('happy')
            self.message.setText(random.choice([
    "Good. 💧",
    "About time.",
    "Finally.",
    "As expected.",
    "That'll do.",
    "At least you listened.",
    "Survived another hour, huh?",
    "Your organs appreciate that.",
    "Nice. Don't make it a rare event.",
    "One crisis avoided.",
    "Hydration maintained.",
    "Acceptable.",
    "I'll count that as a win.",
    "Try doing it again next time.",
    "See? Not that difficult.",
    "Smart choice.",
    "Good. Keep it that way.",
    "The dehydration threat has passed.",
    "For now.",
    "...I'm impressed.",
    "You actually did it.",
    "Better than nothing.",
    "Guess I didn't remind you for nothing.",
    "Your HP has been restored.",
    "Mana restored.",
    "Status effect removed: Dehydrated.",
    "The divine dogs approve.",
    "...Good.",
    "We'll call that progress."
]))

    def no_water(self):
        self.set_buttons_visible(False)
        self.set_mode('sad')
        self.message.setText(random.choice([
            "...figures.",
            "Not surprised.",
            "You skipped it again.",
            "That's unfortunate.",
            "We'll try again later.",
            "Right.",
            "Your decision.",
            "I expected as much.",
            "Still dehydrated, then.",
            "You're making this harder than it needs to be.",
            "I'll be back.",
            "You know this isn't helping.",
            "Ignoring the problem won't fix it.",
            "We'll revisit this in an hour.",
            "That's on you.",
            "Not my best outcome.",
            "You had one job.",
            "Your hydration stats remain questionable.",
            "We'll pretend this didn't happen.",
            "I can't say I'm impressed.",
            "The dehydration risk continues.",
            "Fine.",
            "As you wish.",
            "...okay.",
            "Next time, maybe.",
            "You're remarkably consistent.",
            "Another missed opportunity.",
            "Suit yourself.",
            "Interesting choice.",
            "Let's hope you know what you're doing."
        ]))
        QTimer.singleShot(int(self.config['response_display_ms']) + 1500, self.walk_out)

    def snooze(self):
        self.data['snoozes'] = int(self.data.get('snoozes', 0)) + 1
        save_json(DATA_FILE, self.data)
        self.set_buttons_visible(False)
        self.message.setText(f'Okay, back in {self.config["snooze_minutes"]} min ⏰')
        QTimer.singleShot(1800, self.walk_out)
        if self.snooze_timer:
            self.snooze_timer.stop()
        self.snooze_timer = QTimer(self)
        self.snooze_timer.setSingleShot(True)
        self.snooze_timer.timeout.connect(self.show_reminder)
        self.snooze_timer.start(int(self.config['snooze_minutes'] * 60_000))

    def walk_out(self):
        if not self.isVisible():
            return
        self.set_mode('walk_out')
        current = self.pos()
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        end = QPoint(
            -self.width(),
            current.y()
        )
        self.animation = QPropertyAnimation(self, b'pos')
        self.animation.setDuration(int(self.config['walk_duration_ms']))
        self.animation.setStartValue(current)
        self.animation.setEndValue(end)
        self.animation.setEasingCurve(QEasingCurve.Type.InCubic)
        self.animation.finished.connect(self.hide)
        self.animation.start()

    def show_progress(self):
        self.ensure_today()
        self.message.setText(f'Today: {self.data["water_count"]}/{self.config["daily_goal"]} glasses 💧')
        self.update_counter()
        self.set_buttons_visible(False)
        self.set_mode('legend' if self.data['water_count'] >= self.config['daily_goal'] else 'reminder')
        target, _ = self.target_position()
        self.move(target)
        self.show()
        self.raise_()
        QTimer.singleShot(5000, self.walk_out)

    def reset_today(self):
        self.data = self.default_data()
        self.data['daily_goal'] = int(self.config['daily_goal'])
        save_json(DATA_FILE, self.data)
        self.tray.showMessage('Water Buddy', 'Today’s hydration count was reset.', QSystemTrayIcon.MessageIcon.Information, 2500)

    def play_sound(self):
        sound_path = SOUND_DIR / 'notification.wav'
        if self.config.get('sound_enabled', True) and sound_path.exists():
            self.sound.setSource(QUrl.fromLocalFile(str(sound_path)))
            self.sound.setVolume(0.35)
            self.sound.play()

    def closeEvent(self, event):
        event.ignore()
        self.hide()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    buddy = WaterBuddy()
    sys.exit(app.exec())
