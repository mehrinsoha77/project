# Prerecorded Bangla warning clip

`warning_bangla.mp3` is **not included yet**, on purpose.

The spec requires the Warning voice message to be recorded by a native
speaker from the target reach (Sirajganj / Tangail), in the local variety —
dialect text-to-speech is not good enough, and NadiNet does not synthesise
speech. The dashboard detects that the file is missing and says so; SMS text
and the dispatch path work without it.

Script to record (≈ 20 seconds, calm, clear, slow):

> এটি নদীভাঙন সতর্কবার্তা। আগামী কয়েক সপ্তাহে [গ্রামের নাম] এলাকার নদীতীরে
> ভাঙনের ঝুঁকি বেশি। ঘরের মালামাল ও গবাদিপশু নিরাপদ স্থানে সরানোর প্রস্তুতি নিন
> এবং ইউনিয়ন পরিষদের নির্দেশনা মেনে চলুন।

*This is a riverbank erosion warning. Erosion risk is high along the bank at
[village] in the coming weeks. Prepare to move belongings and livestock to a
safe place, and follow the union parishad's guidance.*

Record one clip per village name (or a generic clip naming the union), save
as mono MP3, 64 kbps, as `warning_bangla.mp3` here, and set
`NADINET_VOICE_CLIP_URL` to its public URL for the Twilio gateway.
