# Echo — setup checklist

You got this project as a zip. This is everything left to do on your end, in
plain steps. Nothing here needs deep coding knowledge — just follow in order.

Two things run independently:
- **Backend** (the "brain" — the AI model + server). Do this first, always.
- **Mobile app** (Flutter). Optional — skip it if you only want the web
  dashboard in a browser.

---

## 0. Install these first

- **Python 3.10 or newer** — https://www.python.org/downloads/ (on the
  installer, tick "Add python.exe to PATH")
- **Flutter SDK** — https://docs.flutter.dev/get-started/install — **only
  if** you want to run the phone app. Skip if the browser dashboard is enough.

Check Python installed correctly: open PowerShell, type `python --version`.
Should print something like `Python 3.12.x`.

---

## 1. Unzip

Unzip the project anywhere simple, e.g. `C:\Echo` (avoid paths with spaces
or very long folder names — Windows can choke on those with Python venvs).

---

## 2. Check if the trained model is already included

Open the folder `model\checkpoints\` in the unzipped project.

- **See files in there** (`yamnet_head.keras`, `echo_yamnet_model.tflite`,
  etc.)? Good — the model is pre-trained and ready. Skip straight to step 4.
- **Folder is empty or missing?** Do step 3 first.

(This folder is normally left out of a plain zip because it's ~55MB of
binary files — check with whoever sent you the zip if you're not sure it was
meant to be included.)

---

## 3. Only if step 2's folder was empty: build + train

Open PowerShell **in the project's root folder** (the one with
`run_local.ps1` in it) and run:

```powershell
.\run_local.ps1 -Setup
```

This will:
1. Create a Python virtual environment (`.venv` folder)
2. Install everything needed (`pip install -r requirements.txt`)
3. Build the training data
4. Train the model

Takes about **10–15 minutes**, needs internet the first time. You'll see a
lot of text scroll by — that's normal. Only needs to be done once.

**If it fails at the "preparing dataset" step** saying it can't find
ESC-50: this project trains on a public sound dataset called ESC-50. If
`model\esc50_temp.zip` isn't in the project already, download it from
https://github.com/karolpiczak/ESC-50/archive/master.zip, rename the
downloaded file to `esc50_temp.zip`, and put it directly inside the `model`
folder. Then run `.\run_local.ps1 -Setup` again.

---

## 4. Start the backend

```powershell
.\run_local.ps1 -Port 8011
```

(Using `8011` instead of the default `8010` — `8010` is sometimes taken by
other software.) Leave this PowerShell window open; closing it stops the
server.

First start takes ~30–90 seconds (it's loading the AI model) — the window
looks stuck but isn't. Wait for a line that says
`Uvicorn running on http://127.0.0.1:8011`.

---

## 5. Open it and try it

Go to **http://127.0.0.1:8011** in your browser.

- Sign in with anything (any email, any password — it's a local demo login,
  nothing is sent anywhere).
- Click the **Demo lab** tab → click **Gunshot** → you should see a red
  alert pop up with a risk score and a countdown.
- Click **Trusted contacts** → add yourself as a contact → **Send test
  alert to my contacts** → confirms the call/message pipeline runs (it'll
  say "simulated" until you do step 6).

If you see that, the backend works. Nothing else to do unless you want real
phone calls/Telegram messages or the mobile app.

---

## 6. Optional: make phone calls + Telegram messages actually happen

By default nothing is actually sent — it's all "simulated" so you can see
what *would* happen. To make it real:

1. In the `backend` folder, copy `.env.example` to a new file named `.env`
2. **Telegram**: open Telegram, message `@BotFather`, send `/newbot`,
   follow the prompts, copy the token it gives you into `.env` as
   `TELEGRAM_BOT_TOKEN=...`
3. **Phone calls**: sign up free at https://twilio.com, get an Account SID,
   Auth Token, and a phone number from the console, paste them into `.env`
   as `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`
4. Phone calls need your backend to be reachable from the internet (Twilio
   fetches the call script from it). Install https://ngrok.com, run
   `ngrok http 8011`, copy the `https://...ngrok...` link it gives you into
   `.env` as `ECHO_PUBLIC_BASE_URL=...`
5. Close and restart the backend (step 4) so it picks up `.env`
6. On the dashboard, add a real contact with a real phone number. For
   Telegram: have that person message your new bot and press Start, then on
   the "Add a contact" form click **Find chats that started my bot** and
   pick them from the list.
7. Click **Send test alert to my contacts** again — this time it should
   really call and message them, clearly labeled as a test.

Skip this whole section if the demo/browser version is all you need.

---

## 7. Optional: run the mobile app

Only do this if you installed Flutter in step 0.

```powershell
cd app
.\setup_app.ps1
flutter run --dart-define=ECHO_API_URL=http://YOUR_COMPUTER_IP:8011
```

Find `YOUR_COMPUTER_IP` by running `ipconfig` in PowerShell and using the
"IPv4 Address" line — only needed if running on a real phone on the same
WiFi. If running in an Android emulator on the same PC, use
`http://10.0.2.2:8011` instead.

This app has **not** been built or run before you do it — you'll be the
first. If `flutter run` shows errors, that's expected on a first build;
common fixes: run `flutter doctor` and follow what it tells you to install,
or ask whoever sent you this project.

---

## Things to know (not bugs — just be honest about them)

- Two of the eight sounds the model detects (**gunshot, scream**) are
  trained only on computer-generated audio, not real recordings — nobody
  has tested them against a real gunshot yet. Everything else (explosion,
  fire alarm, glass breaking, siren, shouting, normal) is trained on real
  recordings.
- Check `reports\evaluation_report.txt` for the actual accuracy numbers if
  you're curious — it's honest, including what still isn't good enough.
- The mobile app's "sudden motion" detector (phone accelerometer) was
  written but never tested on a real device — worth shaking your phone
  once while monitoring to sanity-check it fires.

## If something breaks

- **"Model checkpoint missing"** → go back to step 3.
- **"Port already in use"** → pick a different number, e.g. `-Port 8012`.
- **`pip install` fails** → close and reopen PowerShell, make sure Python
  3.10+, try again.
- **Anything else** → `LOCAL_SETUP.md` in the project root has more detail
  and a list of known quirks.
