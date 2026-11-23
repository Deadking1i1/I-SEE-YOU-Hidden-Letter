# I SEE YOU — the hidden letter

This project contains a procedural binary eye artwork and the encrypted payload for a private letter. The PIN/secret is **not** in this repository; it must be provided to you separately by the sender. The letter is decrypted on your computer and shown in the unlock window. The plaintext is not saved.

## Download and unlock the letter

### 1. Download the project

1. On this GitHub page, select the green **Code** button, then **Download ZIP**.
2. Open the downloaded ZIP in File Explorer and choose **Extract all**.
3. Open the extracted `I-SEE-YOU` folder. Keep the files together; `hidden_message_payload.bin` must stay beside the project files.

### 2. Make sure Python is installed

The unlocker requires Python 3 on Windows. Open PowerShell and run:

```powershell
py --version
```

If Windows says `py` is not recognized, install Python from [python.org/downloads](https://www.python.org/downloads/) and reopen PowerShell.

### 3. Unlock the letter

1. In the extracted project folder, double-click **`unlock_letter.bat`**.
2. On the first run, it installs the small encryption dependency if it is missing. This requires an internet connection; allow it a moment to finish.
3. At `Enter the PIN/secret (typing is hidden):`, type the PIN/secret the sender gave you and press **Enter**. No characters appear while you type.
4. The letter appears in the same window. Press **Enter** when you have finished reading.

The unlocker never puts the PIN/secret in a command, saves it, or writes the decrypted letter to a file. Keep the PIN/secret private. If the prompt rejects it, check that you entered it exactly as provided.

### If double-clicking does not work

Open PowerShell in the extracted project folder, then run:

```powershell
py -m pip install -r requirements-unlock.txt
py tools\read_private_letter.py
```

Enter the PIN/secret only at the hidden prompt. Do not paste it into a command or send it in a GitHub issue or message.

## Run the artwork

Double-click `launch.bat`. It installs the artwork dependencies if needed and opens the animated eye. You can unlock the letter without opening the animation.

## Video extraction (optional)

The project includes an extractor for compatible videos that were made with this project's visual carrier. The supplied WhatsApp video was checked and did not contain recoverable carrier data, so the included encrypted payload is the reliable route for this download.

For a compatible recording, install the optional extractor dependency and run:

```powershell
py -m pip install -r requirements-extractor.txt
py tools\extract_hidden_message.py "C:\path\to\compatible_recording.mp4" --output extracted_payload.bin
py tools\read_private_letter.py --payload extracted_payload.bin
```

## Artwork controls

`Space` pause/resume, `R` restart, `F` fullscreen, `Up`/`Down` speed, `+`/`-` detail, `S` screenshot, and `Esc` exit.

## Dependencies

- Artwork: `requirements.txt`
- Letter unlock: `requirements-unlock.txt`
- Optional video extraction: `requirements-extractor.txt`
