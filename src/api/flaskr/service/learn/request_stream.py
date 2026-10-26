"""Track the terminal message shared by learning and preview requests."""


class RequestCompletion:
    """Finish a request once, without confusing a block boundary with HTTP completion."""

    def __init__(self) -> None:
        """Start with no terminal sent and no consumer cancellation."""
        self.terminal_sent = False
        self.cancelled = False

    @property
    def needs_terminal(self) -> bool:
        """Return whether EOF or a handled error still needs an ephemeral terminal."""
        return not (self.terminal_sent or self.cancelled)

    def record_serialized(self, message: object) -> None:
        """Observe a message only after serialization has succeeded."""
        if isinstance(message, dict):
            message_type = message.get("type")
            terminal = message.get("is_terminal")
        else:
            message_type = getattr(message, "type", None)
            terminal = getattr(message, "is_terminal", None)
        if getattr(message_type, "value", message_type) == "done" and terminal is True:
            self.terminal_sent = True

    def cancel(self) -> None:
        """Prevent any replacement terminal after the consumer disconnects."""
        self.cancelled = True
