"""Turn-level transcript builder (phone ASR, re-transcriptions, chat and secure messages).

Word timings are derived from a speaking rate (or an explicit duration) so that wpm, ordering and
gap-overlap checks computed later from the words reproduce what the builder intended.
"""
from __future__ import annotations

import random
import re
from typing import Optional

from common import stable_hex

DEFAULT_WPM = {"colleague": 160.0, "customer": 150.0}
_PUNCT = re.compile(r"^[^\w$%']+|[^\w$%']+$")


def _clean(token: str) -> str:
    return _PUNCT.sub("", token) or token


class Transcript:
    """Build one transcript. Phone: `turn()` with timings; chat/secure message: `message()` with offsets."""

    def __init__(self, interaction_id: str, channel: str = "phone", source: Optional[str] = None,
                 asr_model: str = "en-US-general", language: str = "en", start_s: float = 1.5,
                 base_conf: float = 0.9, conf_sd: float = 0.05, variant: str = "asr"):
        self.interaction_id = interaction_id
        self.channel = channel
        exact = {"chat": "chat_exact", "secure_message": "message_exact"}
        self.source = source or exact.get(channel, "asr")
        self.asr_model = asr_model if self.source in ("asr", "retranscription") else "none"
        self.language = language
        self.cursor = start_s
        self.base_conf, self.conf_sd = base_conf, conf_sd
        self.rng = random.Random(int(stable_hex(interaction_id, variant, n=16), 16))
        self.turns: list = []
        self.redactions: list = []

    # ------------------------------------------------------------ phone / ASR
    def turn(self, speaker: str, text: str, *, at: Optional[float] = None, dur: Optional[float] = None,
             wpm: Optional[float] = None, pause: float = 0.7, conf: Optional[float] = None,
             word_conf: Optional[dict] = None, speaker_conf: Optional[float] = None,
             speaker_channel: Optional[str] = None, true_speaker: Optional[str] = None) -> dict:
        """Add a spoken turn.

        at: start offset (s); default = previous end + pause.  dur: exact duration; else from wpm.
        conf: mean word confidence for this turn.  word_conf: {word index or cleaned lowercase word: confidence}.
        speaker_channel: stereo channel metadata (defaults to true_speaker or speaker). Set speaker != speaker_channel
        to plant a diarization swap.
        """
        tokens = text.split()
        start = round(self.cursor + pause if at is None else at, 2)
        rate = wpm or DEFAULT_WPM.get(true_speaker or speaker, 155.0)
        total = dur if dur is not None else len(tokens) / rate * 60
        weights = [len(_clean(t)) + 1.5 for t in tokens]
        scale = total / sum(weights)
        words, t = [], start
        mean = self.base_conf if conf is None else conf
        overrides = word_conf or {}
        for i, tok in enumerate(tokens):
            w_dur = weights[i] * scale
            w = _clean(tok)
            c = overrides.get(i, overrides.get(w.lower()))
            if c is None:
                c = min(0.99, max(0.3, self.rng.gauss(mean, self.conf_sd)))
            words.append(dict(w=w, start_s=round(t, 2), end_s=round(t + w_dur, 2), conf=round(c, 2)))
            t += w_dur
        end = round(start + total, 2)
        if words:
            words[-1]["end_s"] = end
        rec = dict(turn_id=f"t{len(self.turns) + 1:02d}", speaker=speaker,
                   speaker_confidence=round(speaker_conf if speaker_conf is not None else self.rng.uniform(0.86, 0.98), 2),
                   speaker_channel=speaker_channel or true_speaker or speaker,
                   start_s=start, end_s=end, text=text, words=words)
        self.turns.append(rec)
        self.cursor = end
        return rec

    def gap(self, seconds: float):
        """Advance the clock (hold, silence, recording gap) without a turn."""
        self.cursor = round(self.cursor + seconds, 2)

    # ------------------------------------------------------------ chat / secure message
    def message(self, speaker: str, text: str, *, at: Optional[float] = None, pause: float = 25.0) -> dict:
        start = round(self.cursor + pause if at is None else at, 2)
        rec = dict(turn_id=f"t{len(self.turns) + 1:02d}", speaker=speaker, speaker_confidence=1.0,
                   speaker_channel=speaker, start_s=start, end_s=start, text=text, words=[])
        self.turns.append(rec)
        self.cursor = start
        return rec

    # ------------------------------------------------------------ output
    def redact(self, turn: dict, kind: str, placeholder: str = "[REDACTED-PAN]"):
        """Replace a placeholder already present in the turn text with a recorded redaction span."""
        i = turn["text"].index(placeholder)
        self.redactions.append(dict(turn_id=turn["turn_id"], type=kind, span=[i, i + len(placeholder)]))

    @property
    def end_s(self) -> float:
        return self.cursor

    def mean_conf(self) -> Optional[float]:
        confs = [w["conf"] for t in self.turns for w in t["words"]]
        return round(sum(confs) / len(confs), 2) if confs else None

    def data(self) -> dict:
        return dict(interaction_id=self.interaction_id, channel=self.channel, source=self.source,
                    asr_model=self.asr_model, language=self.language, turns=self.turns, redactions=self.redactions)


def find_turn(transcript: dict, turn_id: str) -> dict:
    return next(t for t in transcript["turns"] if t["turn_id"] == turn_id)
