# SmartOptics Voice Test — Phase 2 (Cloud / Azure Streaming)

A cloud-hosted version of the voice accuracy test, using Azure Speech in streaming mode. Words appear as you speak. Accessible to the whole team via a single URL — no install required.

---

## Architecture (brief)

```
Browser (Mac/PC) ── PCM audio over WebSocket ──> Render-hosted FastAPI
                <── interim+final transcripts ──   │
                                                   │ Azure Speech SDK
                                                   ▼
                                          Azure Cognitive Services
                                          Speech-to-Text (UK South)
                                          Audio logging: disabled
                                          Phrase list: optical terms
```

**Audio is not stored anywhere.** It is streamed straight through to Azure, transcribed in flight, and discarded. Azure is configured with `audiologging=false`. Aligned with §22.4 of the Voice Input Service spec.

---

## What you need

1. A free **Render** account — https://render.com (sign up with GitHub or email)
2. A free **GitHub** account if you don't have one — https://github.com (Render reads code from a Git repo)
3. Your **Azure Speech key** (KEY 2, which you already have)
4. About 15 minutes for first deploy

---

## Step 1 — Get the code into GitHub

The easiest path is to create a new GitHub repo and upload these files into it.

### Option A — Via GitHub web UI (no command line)

1. Go to https://github.com/new
2. Repository name: `smartoptics-voice-phase2`
3. Set it to **Private**
4. Leave everything else default, click **Create repository**
5. On the next page, click **"uploading an existing file"** (it's in a sentence on that page)
6. Drag the contents of the `phase2` folder (`server.py`, `index.html`, `requirements.txt`, `render.yaml`, this `README.md`) onto the upload area
7. Scroll down, click **Commit changes**

### Option B — Via command line (if you're comfortable with git)

```
cd ~/Desktop/phase2
git init
git add .
git commit -m "Phase 2 voice test harness"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/smartoptics-voice-phase2.git
git push -u origin main
```

---

## Step 2 — Deploy to Render

1. Log into https://render.com
2. Click **New +** (top right) → **Web Service**
3. Choose **"Build and deploy from a Git repository"** → click **Next**
4. Connect your GitHub account if not already connected
5. Find `smartoptics-voice-phase2` in the list → click **Connect**
6. On the configuration screen, Render should auto-detect the `render.yaml` and pre-fill most settings. Confirm:
   - **Name**: `smartoptics-voice-phase2` (or anything)
   - **Region**: Frankfurt (closest free region to UK)
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn server:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free
7. Scroll down to **Environment Variables**:
   - `AZURE_SPEECH_REGION` should already be `uksouth` from render.yaml
   - **You need to add `AZURE_SPEECH_KEY` manually** — click "Add Environment Variable":
     - Key: `AZURE_SPEECH_KEY`
     - Value: paste your Azure KEY 2
   - Make sure it's a **Secret** value (Render handles this automatically for env vars)
8. Click **Create Web Service**

Render will now build and deploy the app. This takes about 3–5 minutes on first deploy.

When it's ready you'll see:
- Status: **Live** (green)
- URL: something like `https://smartoptics-voice-phase2.onrender.com`

That URL is what you share with Zuzana and Romana.

---

## Step 3 — Test it

1. Open the URL in Chrome (or any modern browser)
2. Allow microphone permission
3. Click a test phrase on the right → click the mic → speak → click mic again to stop
4. Words should appear **as you speak** (this is the big difference from Phase 1)

If you see an amber banner warning about the key not being configured — go back to Render's environment variables and confirm `AZURE_SPEECH_KEY` is set, then click **Manual Deploy** → **Deploy latest commit** to restart.

---

## What to expect vs Phase 1

| | Phase 1 (Whisper local) | Phase 2 (Azure streaming) |
|---|---|---|
| Setup | Install Python, ffmpeg, etc on Mac | Open URL in browser |
| Where it runs | Your Mac | Render cloud + Azure cloud |
| Latency | 4 sec after you stop speaking | Words appear during speech, final within ~500ms |
| Accuracy on optical terms | Decent with vocabulary hint | Should be at least as good — Azure has proper phrase-list biasing |
| Who can use it | Just you | Anyone with the URL |

---

## Render free-tier caveats

- **Spins down after 15 min of inactivity.** First request after a gap takes ~30–60 sec to wake up. Subsequent requests are instant until 15 min of silence again.
- **750 hours/month free** — far more than we'll use.
- **WebSockets supported on free tier.** Some hosting services don't allow this; Render does.

For ongoing team testing, this is fine. If you want zero cold-start latency, the cheapest paid tier ($7/month) keeps it always on.

---

## Azure free tier caveats

- **5 hours of audio per month free.** Plenty for team testing — at 30 sec per test phrase that's 600 phrases.
- After 5 hours, transcription stops working until next month rolls over (or you upgrade the Azure tier — S0 pay-as-you-go at ~$1/hour, no automatic spend without you explicitly switching tier).

You can watch usage in Azure portal: search for your Speech resource → Metrics → "Speech recognition transactions" or "Audio Seconds Transcribed".

---

## Updating the app later

Any change you push to the GitHub repo will trigger a redeploy on Render automatically. Useful for adding test phrases, tweaking the UI, etc. Just edit the file in GitHub's web UI, commit, and Render takes care of the rest.

---

## Troubleshooting

**"Server is missing AZURE_SPEECH_KEY" banner**
The env var isn't set. Go to Render dashboard → your service → Environment → confirm `AZURE_SPEECH_KEY` is there with the right value. Click Manual Deploy if needed.

**Mic permission prompt doesn't appear**
Check browser address bar; some browsers put the prompt there instead of as a popup. In Chrome: Settings → Privacy → Site settings → Microphone — ensure the Render URL is allowed.

**WebSocket connect fails**
First request after Render cold-start can fail. Wait 30 seconds, refresh, try again. If it persistently fails, check Render's "Logs" tab for the actual error.

**Azure transcription returns nothing**
- Check key is correct (regenerate KEY 1 in Azure portal if KEY 2 might be stale)
- Check region matches (env var should be `uksouth`)
- Check Azure portal → your Speech resource → Metrics to see if requests are even reaching Azure
- Check Render Logs for the actual Azure error

**Recording starts but transcripts never arrive**
Likely an audio format mismatch. The frontend sends 16kHz/16-bit/mono PCM; if your browser does something unusual the worklet may misbehave. Open browser DevTools (F12) → Console for client errors. Open Render Logs for server errors.

---

## When you're ready to add the team

Just send them the Render URL. They open it in Chrome, allow microphone permission, and they're testing. No install, no account needed.

For collecting their findings — Pass 2 of Phase 2 will add a "Report wrong transcription" button. For now, ask them to note misrecognitions and we'll review together.
