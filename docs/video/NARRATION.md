# Demo video — narration script

**Files**
- `nadinet_demo.mp4`: 1080p, 2:59, on-screen captions and a quiet rain-like background. Ready to upload as is.
- `nadinet_demo_no_audio.mp4`: the same picture with no sound, for recording your own voice.
- `thumbnail.png`: 1280×720, for YouTube or Vimeo, and the Devpost gallery.

**Why no synthetic voice:** text-to-speech always sounds artificial. A real voice, even recorded on a phone, sounds more trustworthy to judges. The captions carry the whole story if you upload without narration.

## How to add your voice (10 minutes)

1. Read the lines below aloud once or twice. Then record them on your phone in a quiet room, speaking a little slower than normal.
2. Open `nadinet_demo_no_audio.mp4` in any editor (CapCut, iMovie, DaVinci Resolve or Clipchamp; all free). Drop your recording on the audio track and line each line up with its timestamp.
3. Optional: add `nadinet_demo.mp4`'s rain bed underneath at a low level, and turn it down under your voice.
4. Export at 1080p and upload to YouTube (Unlisted is fine) or Vimeo, with `thumbnail.png` as the thumbnail. Paste that link into Devpost.

## Lines to read

The timestamps are when each line should start. Pauses are fine; the picture waits for you.

| Time | Say | On screen |
|---|---|---|
| 0:00 | "This is NadiNet." *(pause)* | Title card |
| 0:07 | "Every monsoon, the Jamuna river in Bangladesh swallows homes, farmland and embankments. Riverbank erosion forces an estimated fifty thousand to two hundred thousand people from their homes every year — and most of it happens when the river is hidden under cloud." | Problem card |
| 0:23 | "This is July 2025, at the peak of the monsoon. The optical satellite sees almost nothing — ninety-nine percent cloud." | Cloudy Sentinel-2 image |
| 0:30 | "But radar sees straight through. Here's the same week from Sentinel-1: the water is dark, the land is bright, and you can see both banks." | Slider reveals the radar |
| 0:35 | "NadiNet uses this free radar after every pass — and we test every forecast against what actually happened." | Landing page |
| 0:45 | "A new radar image arrives every twelve days. We trace both banks of the river on eight hundred and seventy-one segments, each two hundred metres long." | Monsoon playback |
| 0:53 | "The dashed line is where the bank started the season. The blue line is where it is now." | Bank lines moving |
| 1:01 | "Now we freeze the model on the twelfth of July 2023. It only knows what the radar had seen up to that day." | "The model only knows data up to…" |
| 1:06 | "It ranks the twenty stretches most likely to lose land in the next four weeks, and says why, in plain language." | Top 20 with reasons |
| 1:14 | "For comparison, here's the obvious guess: the twenty places that eroded most recently." | Persistence top 20 |
| 1:22 | "Now we reveal what really happened. Green means we flagged it and it eroded. Red means it eroded and we missed it." | Map turns green and red |
| 1:29 | "On this day, nine of our twenty really lost land. The obvious guess got none." | Result banner |
| 1:35 | "You can open any stretch and see its whole history since 2015, and exactly what happened next." | Segment card |
| 1:47 | "Across every test date from 2023 to 2025 — years the model never saw — forty-two percent of our top twenty really eroded. The obvious guess: four percent." | Precision chart |
| 1:56 | "For local officials, there's a dashboard with the latest pass, the ranked list and a weekly briefing they can print." | Dashboard |
| 2:12 | "When it's serious, a warning is drafted in Bangla, as a text message and a voice call." | Bangla SMS draft |
| 2:21 | "But nothing reaches families until a named official approves it. The software never sends a public warning on its own." | Approval |
| 2:31 | "Every number you've seen is measured and published. Our bank lines match independent satellite images to within twenty metres." | Results page |
| 2:39 | "And we keep a ledger of what we've measured, what we haven't built yet, and what we refused to claim." | Claims ledger |
| 2:50 | "NadiNet. Free radar, honest numbers, and human decisions — so families can move before the river does." | End card |

## Numbers used (all measured; see `docs/CLAIMS_LEDGER.md`)

- 271 Sentinel-1 passes, 2015–2025; 871 bank segments of 200 m.
- On 12 July 2023, with the next check on 5 August 2023: 9 of the model's top 20 lost ≥ 40 m; persistence 0 of 20; 26 segments lost land in total.
- Over 65 held-out dates, 2023–2025: precision@20 42.3% vs 4.1% for persistence.
- Bank lines agree with Sentinel-2 to a 20 m median error.
- Displacement estimate (context, not ours): 50,000–200,000 people a year in Bangladesh, from RMMRU / Sussex (2013).

## Rebuilding the video

`docs/video/source/` holds the recorder (`record.mjs`, Playwright) and the title and end cards. Start the app (`bash scripts/start_demo.sh`), then run:

```bash
node docs/video/source/record.mjs docs/video/source   # writes source/raw/*.webm and captions.json
```

Then encode as in the commit history (ffmpeg: upscale 1440×810 → 1920×1080 with lanczos, fade in and out).
