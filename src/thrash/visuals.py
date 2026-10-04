"""Pressure effects are representations of measured state, never new metrics."""
from dataclasses import dataclass

LEVELS = {'NORMAL': 0, 'PRESSURE': 1, 'THRASHING': 2, 'PANIC': 3}


@dataclass
class VisualPressure:
    level: int = 0
    phase: int = 0

    def tick(self, mode, reduced_motion=False):
        target = LEVELS[mode]
        self.phase += 1
        # Escalate immediately; shed one visual layer per tick during recovery.
        self.level = target if reduced_motion or target >= self.level else self.level-1
        return self.level

    def offset(self, reduced_motion=False):
        return 0 if reduced_motion or not self.level else self.phase % (self.level+1)
