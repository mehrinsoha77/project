# Demo script

The demo is a **replay of real history**, not a live satellite fetch: the
model is frozen at a past date and the audience watches what actually
happened next. Everything is precomputed and runs offline
(`bash scripts/start_demo.sh`, or just `cd app && npm run dev`).

Rehearse at least five full runs. Fallbacks are at the end.

## 30 seconds — the wow moment

1. Open the landing page. The right-hand image is a **real Sentinel-2 scene
   of the reach in the monsoon** — almost all cloud (cloud percentage and
   date are printed on it).
2. Drag the slider: the **Sentinel-1 radar pass of the same week** appears
   underneath. The river and both banks are there.
3. Click **Watch the replay** → step 1 *Watch the monsoon*. Press play: bank
   lines pass by pass through that monsoon (dashed = first pass, blue = the
   pass shown). Pause on a segment that visibly moves.
4. Line: *"Optical satellites saw nothing for weeks. Radar saw the bank move
   on every pass."*

## 3 minutes — the proof

1. Open with the 30-second sequence.
2. Step 2 **Freeze the model**. Read the banner: *"The model only knows data
   up to {date}"*, with the date filter shown in code.
3. Show the **top 20** segments, each with its plain-language reason. Toggle
   **Persistence top 20** to show what "it eroded recently" would have picked.
4. Step 3 **Reveal 28 days later**. Hits turn green, missed erosion red,
   false alarms grey. Read the banner: hits for the model vs persistence on
   this date.
5. Scroll to **Every held-out forecast date**: the per-date precision@20
   chart, model vs persistence, and the mean difference with its 95% CI.
   **Read the measured numbers from the claims ledger, always beside the
   persistence baseline.** If the model does not beat persistence on a date,
   say so — the chart shows it anyway.
6. Open the **Dashboard → Alerts** tab. Select a Warning-eligible segment,
   type a union name, *Draft Warning for official review*. An "official"
   enters a name and role and approves. With the API running, the console
   gateway writes the SMS and the voice call to the outbox (or Twilio rings the
   test phone, if configured). Show the Bangla text on screen.

## 10 minutes — the deep dive

1. **Pipeline** (Method & evidence page, §1): GRD window read → σ⁰ → Lee →
   GCP geocoding → Otsu mask → braid belt → transects.
2. **Detection check**: the Sentinel-2 comparison, the measured bank error,
   and the story of the **100 m geolocation shift** found and corrected — the
   kind of thing you only find by measuring.
3. **Labels**: forward confirmation; why flood edges are not erosion.
4. **Feature importance and ablations**, including that coherence was not
   built (and so no claim is made about it).
5. **Reliability diagram**: does 30% mean 30%?
6. **Two or three failures**: pick misses (red) on the replay and open the
   segment history — e.g. a sudden retreat with no prior activity, or a
   segment near the bridge.
7. **Limitations** and what a partner pilot would add (ground reports,
   FFWC levels, a second track).

## Skeptic test

A judge picks **any forecast date in 2023–2025** (dropdown) and **any
segment** (click the map). The segment card shows its bank history **cut at
the forecast date**, the model's risk and reasons, and only after *Reveal*
the passes after that date and the outcome. The date filter is in the banner.
The no-leakage unit test (`pytest tests/test_no_leakage.py`) can be run live.

## Fallbacks

* **No network**: nothing changes — all maps, rankings, charts and PDF
  briefs are in `app/public/data`. The street-map toggle is the only online
  feature.
* **API won't start**: the dashboard detects it and runs alerts in
  *offline demo mode* (clearly labelled; nothing is sent; logged in the
  browser).
* **Alert gateway fails**: show the outbox (`data/processed/alerts/outbox.jsonl`)
  and the Bangla text on screen. The voice clip itself must be a recording by
  a native speaker from the reach; until it exists, say so.
* **Projector too dark for radar**: switch the site to light theme (moon
  icon); the map stays dark by design.
