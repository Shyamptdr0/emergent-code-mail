# MailTrack — Chrome Extension

Tracks Gmail email opens with gray → green ticks and desktop notifications.

## Install (developer mode)
1. Open `chrome://extensions` in Chrome
2. Toggle **Developer mode** (top right)
3. Click **Load unpacked** and select this `extension/` folder
4. Click the MailTrack icon, paste:
   - **Backend URL**: from your dashboard → Settings
   - **API key**: from your dashboard → Settings
5. Open Gmail. Compose & send — emails are auto-tracked.

## What it does
- Adds `✓✓ tracked` badge in compose view
- Injects a 1×1 tracking pixel at the end of each email
- Renders gray (sent) / green (opened) ticks beside subject lines in the Sent folder
- Polls backend every 30 seconds; sends desktop notification on open
- Surfaces follow-up reminders when due
