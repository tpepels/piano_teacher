# Japanese spoken count-in (bundled offline)

All four Ogg Vorbis clips are **committed directly into this repository** and
ship with the application. There is no network request, download installer,
background task or external speech service on startup or during practice.

| Count | File | Wikimedia Commons source | Creator | License |
| --- | --- | --- | --- | --- |
| Ichi | `ichi.ogg` | [Ja-1-ichi.ogg](https://commons.wikimedia.org/wiki/File:Ja-1-ichi.ogg) | Marsian | Public domain (PD-self) |
| Ni | `ni.ogg` | [Ja-2-ni.ogg](https://commons.wikimedia.org/wiki/File:Ja-2-ni.ogg) | Marsian | Public domain (PD-self) |
| San | `san.ogg` | [Ja-3-san.ogg](https://commons.wikimedia.org/wiki/File:Ja-3-san.ogg) | Marsian | Public domain (PD-self) |
| Shi | `shi.ogg` | [Ja-4-shi_counting.ogg](https://commons.wikimedia.org/wiki/File:Ja-4-shi_counting.ogg) | Marsian | Public domain (PD-self) |

Godot loads the original Ogg files from `res://assets/countin/` directly.
Playback begins around 0.21 seconds into each clip to remove the recorded
leading silence. The backend's beat controls when each utterance starts; the
countdown never owns or changes the transport clock.

Voice is enabled by default and can be disabled under Practice > More.
The preference persists in `user://countin_voice.cfg`. The metronome click
remains a fallback only when speech is disabled or an asset cannot be loaded.

For maintainers only: `python3 scripts/fetch_countin_voices.py --verify`
checks the shipped assets; running without `--verify` reacquires missing
originals from Wikimedia with HTTP 429 backoff. Releasing without all four
assets is rejected by `tests/godot/countin_voice_assets.gd`.
