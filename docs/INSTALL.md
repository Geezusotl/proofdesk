# Install ProofDesk (no technical skills needed)

ProofDesk runs on your own computer. Your documents never leave it.

## Windows

1. Go to https://github.com/Geezusotl/proofdesk/releases/latest
2. Under **Assets**, click **ProofDesk-Windows.zip** to download it.
3. Open your Downloads folder, right-click the zip, choose **Extract All**, then **Extract**.
4. Open the new folder and double-click **ProofDesk**.
5. If Windows says **"Windows protected your PC"**, click **More info**, then **Run anyway**. This appears for every app that isn't from a big company. ProofDesk is open source, so you can read all of it.
6. A black window opens and then your web browser opens with ProofDesk. Leave the black window open while you use it. Close it to stop ProofDesk.

## Mac

1. Go to https://github.com/Geezusotl/proofdesk/releases/latest
2. Under **Assets**, click **ProofDesk-Mac.zip**. Double-click the downloaded zip to unzip it.
3. **Right-click** (or Control-click) **ProofDesk**, choose **Open**, then click **Open** again. Do this the first time only; Mac blocks a plain double-click on apps from small developers.
4. A window opens and then your web browser opens with ProofDesk. Close the window to stop it.

If that doesn't work (older Intel Macs): download **Source code (zip)** from the same page, unzip it, and right-click **Start ProofDesk.command** > **Open**. This needs Python from https://www.python.org/downloads/, and the window tells you if it's missing.

## Linux

Download **ProofDesk-Linux.zip**, unzip it, then run `chmod +x ProofDesk && ./ProofDesk`.

## First five minutes

When ProofDesk opens, a **Guide** card walks you through it. Click **Next** and **Ask**-style buttons on the card. It uses a made-up company handbook, so you can try it without any files of your own.

To use your own files, click **Add document** and paste text or choose a `.txt` or `.md` file. Word and PDF files aren't supported yet: copy the text out of them and paste it in.

## Something went wrong?

| What you see | What to do |
|---|---|
| Nothing happens when you double-click | Wait 10 seconds; the first start is slow. |
| Browser didn't open | Look at the black window: it prints an address like `http://127.0.0.1:8765/`. Type that into your browser. |
| "Port is busy" | ProofDesk is probably already open in another window. Close it, or use the address it prints. |
| Windows or Mac says the app is unsafe | Follow step 5 (Windows) or step 3 (Mac) above. |
| Python not found (Start ProofDesk file) | Use the ProofDesk-Windows/Mac zip instead, which needs no Python. |

## Remove it

Delete the folder. ProofDesk installs nothing else and keeps no files.
