# Motorized Stage — Gamidor

בקר תנועה לסטייג' מבוסס

`ESP32 DevKit V1`

עם דרייבר

`TMC2209`

מנוע

`NEMA 17 (17HS3401)`

ואופטי endstop להחזרה לאפס.

הפרוייקט מורכב משני חלקים:

1. קושחת ESP32

2. אפליקציית בקרה ב-Python למחשב

---

## מבנה תקיות

```
motorized-stage/
├── firmware/
│   └── MotorizedStage.ino
├── controller/
│   ├── stage_controller.py
│   ├── config.json
│   └── requirements.txt
└── README.md
```

---

## חיבורי חומרה

הפינים נעולים בקושחה. אסור לשנות בלי לעדכן את

`MotorizedStage.ino`

| רכיב | פין ESP32 | הערה |
|------|-----------|------|
| TMC2209 EN | GPIO 26 | Active LOW |
| TMC2209 DIR | GPIO 27 | |
| TMC2209 STEP | GPIO 14 | |
| TMC2209 VDD | 3.3V | לוגיקה |
| TMC2209 VM | 24V PSU | כוח מנוע |
| Endstop S | GPIO 32 | INPUT_PULLUP, trigger LOW |
| Endstop V | 3.3V | |
| GND משותף | כל הרכיבים | חובה |

לוגיקה ברמת

`3.3V`

בלבד.

---

## פרוטוקול סריאל

קצב:

`115200 baud`

פקודות (מסיימות ב-newline):

| פקודה | פעולה | תשובה |
|--------|--------|--------|
| `INIT` | Homing אחורה בלבד עד endstop, מאפס מיקום | `BUSY` ואז `HOME_DONE` |
| `POS1` | מעבר ל-POS1 מהקושחה | `BUSY` ואז `DONE` |
| `POS2` | מעבר ל-POS2 מהקושחה | `BUSY` ואז `DONE` |
| `GOTO <abs>` | מעבר למיקום מוחלט | `BUSY` ואז `DONE` |
| `SPEED <v>` | שינוי מהירות מקסימלית בזמן ריצה | `OK SPEED <v>` |

הקושחה מחזירה

`READY`

בעליה ו-

`ERR <msg>`

על שגיאה.

מגבלה חשובה ב-INIT: המנוע תמיד נע בכיוון שלילי. אסור גלישה קדימה.

---

## קושחה - הקלדה והעלאה

ב-Arduino IDE:

1. התקן ESP32 board support דרך Boards Manager.

2. בחר לוח

`ESP32 Dev Module`

3. התקן ספרייה

`AccelStepper`

דרך Library Manager.

4. פתח

`firmware/MotorizedStage.ino`

5. Upload.

---

## אפליקציית מחשב

תלויות:

`pyserial>=3.5`

הרצה במצב פיתוח:

```
cd controller
pip install -r requirements.txt
python stage_controller.py
```

הקובץ

`config.json`

נטען מהתקייה ליד ה-exe (או ליד ה-py בפיתוח). אם הוא חסר, נוצר אוטומטית עם ברירת מחדל.

שדות:

| שדה | תיאור |
|------|--------|
| `COM_PORT` | שם הפורט או `"Auto"` לזיהוי אוטומטי |
| `BAUD_RATE` | תמיד 115200 |
| `POS1_VALUE` | יעד POS1 בצעדים (לצפייה ב-GUI) |
| `POS2_VALUE` | יעד POS2 בצעדים (לצפייה ב-GUI) |
| `DEFAULT_SPEED` | נשלח אוטומטית בעת חיבור |
| `MOVE_TIMEOUT_SEC` | טיים-אאוט עתידי |

הערה: ערכי

`POS1_VALUE`

ו-

`POS2_VALUE`

מהקונפיג הם תווית תצוגה בלבד. היעדים האמיתיים מוגדרים בקושחה כ-

`TARGET_POS1`

ו-

`TARGET_POS2`

כדי לעמוד בדרישת המקור (פקודות POS1/POS2 מבצעות יעד שמור בקושחה). אם רוצים שהקונפיג יקבע את היעד, יש להחליף את

`POS1`

ב-

`GOTO <POS1_VALUE>`

בצד הפייתון.

---

## קומפילציה ל-EXE עצמאי

PyInstaller, שיטה ידנית מומלצת:

```
cd controller
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed ^
    --name GamidorStage ^
    --add-data "config.json;." ^
    stage_controller.py
```

הסבר דגלים:

| דגל | מה עושה |
|-----|----------|
| `--onefile` | exe יחיד |
| `--windowed` | בלי חלון cmd ברקע |
| `--name` | שם פלט |
| `--add-data` | מצרף config.json לתוך bundle |

פלט נמצא ב-

`controller/dist/GamidorStage.exe`

מומלץ להעתיק לידו גם

`config.json`

חיצוני - האפליקציה קוראת קודם מהתקייה של ה-exe, מה שמאפשר שינוי הגדרות בלי בנייה מחדש.

---

### חלופה ידידותית - auto-py-to-exe

```
pip install auto-py-to-exe
auto-py-to-exe
```

ב-GUI:

1. Script Location -> `stage_controller.py`

2. Onefile

3. Window Based (hide console)

4. Additional Files -> הוסף `config.json`

5. Convert .py to .exe

---

## פתרון תקלות

| תסמין | סיבה אפשרית |
|--------|---------------|
| Auto לא מוצא פורט | חבר ESP32 דרך USB, התקן דרייבר CP210x/CH340 |
| ERR NOT_HOMED | הרץ INIT לפני תנועה |
| המנוע לא זז | בדוק 24V ב-VM, EN חוטי, GND משותף |
| Homing לא נעצר | בדוק קוטביות endstop, התאם `ENDSTOP_TRIGGERED_LEVEL` |
| תנודות / איבוד צעדים | הורד `DEFAULT_MAX_SPEED` או `DEFAULT_ACCEL` |
