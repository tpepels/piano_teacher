# Japanese spoken count-in

The four Ogg Vorbis samples are cached by `scripts/fetch_countin_voices.py` on
the first `./run.sh` launch. There is no network access during practice.
When a sample is absent, the existing metronome click is used for that beat.

| UI | Source file | Author | License |
| --- | --- | --- | --- |
| Ichi | [Ja-1-ichi.ogg](https://commons.wikimedia.org/wiki/File:Ja-1-ichi.ogg) | Marsian | Public domain (PD-self) |
| Ni | [Ja-2-ni.ogg](https://commons.wikimedia.org/wiki/File:Ja-2-ni.ogg) | Marsian | Public domain (PD-self) |
| San | [Ja-3-san.ogg](https://commons.wikimedia.org/wiki/File:Ja-3-san.ogg) | Marsian | Public domain (PD-self) |
| Shi | [Ja-4-shi_counting.ogg](https://commons.wikimedia.org/wiki/File:Ja-4-shi_counting.ogg) | Marsian | Public domain (PD-self) |

These original recordings are about one second long and include about 0.25 s
of leading silence. Godot starts playback 0.21 s into the sound at the beat
boundary, without changing the backend's transport or grading clock.

Voice is enabled by default. Toggle it in Practice > More. The choice persists
locally in `user://countin_voice.cfg`. If a machine is offline at first
launch, run `python3 scripts/fetch_countin_voices.py` when connected.
Set `PIANO_TEACHER_VOICE_DOWNLOAD=0` to skip installation deliberately.
