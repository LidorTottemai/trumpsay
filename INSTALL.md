# הוראות התקנה — Trump Market Predictor על Raspberry Pi

## דרישות מקדימות

- Raspberry Pi עם Raspberry Pi OS Bookworm (64-bit מומלץ)
- Python 3.11 ומעלה (`python3 --version`)
- חיבור לאינטרנט
- בוט טלגרם פעיל + ה-Chat ID של הערוץ

---

## שלב 1 — עדכון המערכת והתקנת תלויות מערכת

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv python3-dev python3-lxml git
```

> **חשוב:** `python3-lxml` מותקן דרך apt כדי להימנע מקומפילציה ארוכה על ה-Pi.

---

## שלב 2 — הורדת הפרויקט

```bash
cd /home/pi
git clone https://github.com/LidorTottemai/trumpsay.git
cd trumpsay
```

---

## שלב 3 — יצירת סביבה וירטואלית

```bash
python3 -m venv venv --system-site-packages
```

> `--system-site-packages` מאפשר לסביבה הוירטואלית להשתמש ב-lxml שהותקן דרך apt.

---

## שלב 4 — התקנת חבילות Python

```bash
source venv/bin/activate
pip install --upgrade pip
pip install feedparser --no-deps
pip install -r requirements.txt
```

> `feedparser --no-deps` נדרש כי תלות `sgmllib3k` שלו לא מתקמפלת תקין.

---

## שלב 5 — הגדרת משתני סביבה

```bash
cp .env.example .env
nano .env
```

מלא את הפרטים הבאים:

```env
ANTHROPIC_API_KEY=sk-ant-...          # מפתח API של Anthropic
TELEGRAM_BOT_TOKEN=12345:ABCdef...    # טוקן הבוט מ-@BotFather
TELEGRAM_CHAT_ID=-100123456789        # ID של הערוץ (מינוס בהתחלה לערוץ)

# אופציונלי
NEWSAPI_KEY=                          # השאר ריק אם אין לך מפתח
SEND_HOUR=14                          # שליחה ב-14:00 שעון ישראל
SEND_MINUTE=0
TIMEZONE=Asia/Jerusalem
CLAUDE_MODEL=claude-opus-4-7
LOG_LEVEL=INFO
DRY_RUN=false
```

שמור וצא: `Ctrl+O` → `Enter` → `Ctrl+X`

---

## שלב 6 — בדיקות

### בדיקת שליפת נתונים (ללא קריאה ל-Claude)
```bash
source venv/bin/activate
python main.py test-fetch
```
צפה לרשימה של 5–30 פריטים ממקורות שונים.

### הרצה אחת עם הדפסה למסך (ללא שליחה לטלגרם)
```bash
python main.py once --dry-run
```
צפה להודעה בעברית עם תחזית שוק מלאה.

### בדיקת שליחה לטלגרם
```bash
python main.py test-telegram
```
תקבל הודעת בדיקה בערוץ הטלגרם שלך.

### הרצה אחת מלאה (שולח לטלגרם)
```bash
python main.py once
```

---

## שלב 7 — הגדרת שירות systemd (הרצה אוטומטית)

```bash
sudo cp trumpsay.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable trumpsay
sudo systemctl start trumpsay
```

בדיקת סטטוס:
```bash
sudo systemctl status trumpsay
```

---

## צפייה ביומן לוגים

```bash
# לוגים חיים
sudo journalctl -u trumpsay -f

# לוגים של היום
sudo journalctl -u trumpsay --since today

# לוגים 100 שורות אחרונות
sudo journalctl -u trumpsay -n 100
```

---

## עדכון הפרויקט

```bash
cd /home/pi/trumpsay
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart trumpsay
```

---

## תיעוד תוצאות שוק (לשיפור עתידי)

לאחר כל יום מסחר, ניתן לרשום את התוצאה האמיתית של ה-S&P 500:

```bash
source venv/bin/activate
python main.py record-outcome --date 2026-05-20 --sp500 +1.4
```

הנתונים נשמרים ב-`data/history.db` ומשמשים להקשר היסטורי בניתוחים עתידיים.

---

## פתרון בעיות

| בעיה | פתרון |
|------|--------|
| `No module named feedparser` | `pip install feedparser --no-deps` |
| `lxml build failed` | `sudo apt install python3-lxml` ואז `venv --system-site-packages` |
| `Telegram bot token is invalid` | בדוק `TELEGRAM_BOT_TOKEN` ב-.env |
| `bot cannot send to chat` | הוסף את הבוט לערוץ כמנהל עם הרשאות שליחה |
| אין נתונים בשליפה | בדוק חיבור לאינטרנט, הרץ `python main.py test-fetch` |
| השירות לא עולה | `sudo journalctl -u trumpsay -n 50` לראיית השגיאה |
