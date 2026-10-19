# Water Buddy

## 1. Add your GIFs
Copy these five files into `assets` with these exact names:

- `walk in.gif`
- `reminder mode.gif`
- `happy mode.gif`
- `sad mode.gif`
- `hydration legend mode.gif`

Optional:
- `assets/icon.png` for the system tray
- `sounds/notification.wav` for the reminder sound

Important: a grey checkerboard inside a GIF is not transparency. Export each GIF with a genuinely transparent background.

## 2. Install and run on Windows
Open PowerShell inside this folder and run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py main.py
```

For a quick test, set `reminder_minutes` to `0.2` in `config.json` (12 seconds). Change it back to `60` afterward.

## 3. Create a Windows EXE
With the virtual environment active:

```powershell
py -m pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --name WaterBuddy --add-data "assets;assets" --add-data "sounds;sounds" --add-data "config.json;." main.py
```

The result will be in `dist\WaterBuddy`.

## Controls
- **Yep**: increments today's count and plays Happy or Hydration Legend mode.
- **Later**: snoozes for the configured number of minutes.
- **Nope**: plays Sad mode.
- Click the tray icon: show a reminder now.
- Right-click tray icon: progress, reset, or quit.
