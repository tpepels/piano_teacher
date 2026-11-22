"""Validated manual teaching requests and exact progress application.

The engine supplies facts under its lock; this owner never receives the engine
or a callback bag. Infrastructure acknowledgements do not create decisions.
"""
from contextlib import contextmanager


class SessionCommands:
    def __init__(self):
        self.action_reason = "transition"

    @contextmanager
    def reason(self, action: str):
        """Restore the original reason even when command preparation fails."""
        previous = self.action_reason
        self.action_reason = action
        try:
            yield
        finally:
            self.action_reason = previous



