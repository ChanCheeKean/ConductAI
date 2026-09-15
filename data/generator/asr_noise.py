"""Deterministic lightweight ASR and diarization noise for background calls."""
from __future__ import annotations

from transcripts import Transcript

CONFUSIONS = {"yes": "yeah", "no": "know", "fee": "free", "fifteen": "fifty", "three": "free",
              "cancel": "can sell", "interest": "interests"}


def noisy(text: str, rng, severity: float = .08) -> str:
    words = text.split()
    out = []
    for word in words:
        clean = word.lower().strip(".,?!")
        if rng.random() < severity * .12:
            continue
        out.append(CONFUSIONS.get(clean, word) if rng.random() < severity else word)
        if rng.random() < severity * .04:
            out.append("uh")
    return " ".join(out)


def call(interaction_id: str, lines: list[tuple[str, str]], rng, *, language="en", wrong_model=False,
         swap=False, wpm=160) -> Transcript:
    model = "en-US-general" if language == "en" or wrong_model else "es-US-general"
    base = .50 if wrong_model else (.83 if language == "es" else .86)
    t = Transcript(interaction_id, "phone", asr_model=model, language=language, base_conf=base, conf_sd=.06)
    for n, (speaker, text) in enumerate(lines):
        rendered = noisy(text, rng, .28 if wrong_model else .06)
        shown = ("customer" if speaker == "colleague" else "colleague") if swap and n == 2 else speaker
        t.turn(shown, rendered, wpm=wpm, true_speaker=speaker, speaker_channel=speaker,
               speaker_conf=.38 if swap and n == 2 else None)
    return t
