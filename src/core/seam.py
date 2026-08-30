"""Finding the cut that makes a join invisible.

Joining two clips leaves a visible jump unless the frame the first one ends on
and the frame the second one starts from look alike. Rather than have someone
scrub for it, the incoming clip is searched for the frame closest to the
outgoing one and its time is offered as the in point.

Closeness is not one number. Three things go wrong at a cut, and they fail
independently:

* **Colour** — the obvious one. A plain per-pixel difference catches a change of
  scene or of lighting, and nothing else.
* **Structure** — comparing edges instead of pixels survives a slow exposure
  drift that would swamp a pixel difference, while still refusing two frames
  whose contents have actually moved.
* **Motion** — two frames can match perfectly and still jar, because one is the
  middle of a pan and the other is a standstill. Comparing each frame against
  its own neighbour approximates which way things were travelling, so a cut is
  only called good when the movement continues too.

The weights follow the Clip to GIF tab's loop finder, which solves the same
problem at the two ends of one clip rather than between two.

Depends on numpy and Pillow only; nothing here imports PyQt6.
"""
from typing import List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

# Small enough that a search over a few hundred candidates is instant, large
# enough that two different scenes never score as a match.
SIGNATURE_SIZE = (64, 64)

WEIGHT_COLOUR = 0.6
WEIGHT_EDGES = 0.2
WEIGHT_MOTION = 0.2

# Calibrated by measuring the score between known pairs of a moving clip:
# neighbouring frames land near 0.0005, five frames apart near 0.004, opposite
# ends of the same shot near 0.017, and a different scene near 0.12. So a couple
# of frames of drift is seamless, anything still inside the same shot is close,
# and a different scene cannot be mistaken for either.
#
# These only put words to a number. Nothing is rejected on them: the best
# available match is still the best available match, and the caller is told the
# score so it can say how good it actually is.
SEAMLESS = 0.004
CLOSE = 0.025


def signature(image: Image.Image) -> np.ndarray:
    """The small RGB array every comparison is actually made on."""
    small = image.convert("RGB").resize(SIGNATURE_SIZE, Image.Resampling.BILINEAR)
    return np.asarray(small, dtype=np.float32) / 255.0


def _edges(sig: np.ndarray) -> np.ndarray:
    """Gradient magnitude of the greyscale image, as a stand-in for structure."""
    grey = sig.mean(axis=2)
    gx = np.abs(np.diff(grey, axis=1, append=grey[:, -1:]))
    gy = np.abs(np.diff(grey, axis=0, append=grey[-1:, :]))
    return np.sqrt(gx * gx + gy * gy)


def _mse(a: np.ndarray, b: np.ndarray) -> float:
    diff = a - b
    return float(np.mean(diff * diff))


def distance(a: np.ndarray, b: np.ndarray,
             a_next: Optional[np.ndarray] = None,
             b_next: Optional[np.ndarray] = None) -> float:
    """How badly a cut from `a` to `b` would show. 0 means identical.

    `a_next` and `b_next` are the frames that follow each of them in their own
    clips. Given both, the motion term is included; without them the score is
    colour and structure only, which is the right answer for a still.
    """
    score = WEIGHT_COLOUR * _mse(a, b) + WEIGHT_EDGES * _mse(_edges(a), _edges(b))
    if a_next is not None and b_next is not None:
        score += WEIGHT_MOTION * _mse(a_next - a, b_next - b)
    else:
        # Without motion to judge, the remaining terms carry the whole score
        # rather than the result being flattered by a missing component.
        score /= (WEIGHT_COLOUR + WEIGHT_EDGES)
    return float(score)


def find_match(target: Image.Image, candidates: Sequence[Image.Image], *,
               target_next: Optional[Image.Image] = None,
               search: Optional[Sequence[int]] = None
               ) -> Tuple[Optional[int], float]:
    """Index of the candidate that follows `target` most cleanly, and its score.

    `search` restricts which candidate indices are considered, which is how the
    caller keeps the in point from landing past the out point. Returns
    (None, inf) when there is nothing to choose from.
    """
    if not candidates:
        return None, float("inf")
    indices = list(search) if search is not None else list(range(len(candidates)))
    indices = [i for i in indices if 0 <= i < len(candidates)]
    if not indices:
        return None, float("inf")

    target_sig = signature(target)
    target_next_sig = signature(target_next) if target_next is not None else None

    sigs: dict = {}

    def sig_at(i: int) -> np.ndarray:
        if i not in sigs:
            sigs[i] = signature(candidates[i])
        return sigs[i]

    best_index, best_score = None, float("inf")
    for i in indices:
        nxt = sig_at(i + 1) if (target_next_sig is not None
                                and i + 1 < len(candidates)) else None
        score = distance(target_sig, sig_at(i),
                         a_next=target_next_sig if nxt is not None else None,
                         b_next=nxt)
        if score < best_score:
            best_index, best_score = i, score
    return best_index, best_score


def describe(score: float) -> str:
    """Plain words for a score, so the number does not have to mean anything."""
    if score <= SEAMLESS:
        return "seamless"
    if score <= CLOSE:
        return "close"
    return "no good match"
