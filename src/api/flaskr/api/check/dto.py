"""Define request and response DTOs for risk checks."""

CHECK_RESULT_PASS = 0
CHECK_RESULT_REVIEW = 1
CHECK_RESULT_REJECT = 2
CHECK_RESULT_UNKNOWN = 3
CHECK_RESULT_UNCONF = 4


class CheckResultDTO:
    """Represent the check result API payload."""

    check_result: int
    risk_labels: list[str]
    risk_label_ids: list[int]
    provider: str

    def __init__(
        self,
        check_result: int,
        risk_labels: list[str],
        risk_label_ids: list[int],
        provider: str,
        raw_data: dict,
    ) -> None:
        """Build a moderation check-result payload."""
        self.check_result = check_result
        self.risk_labels = risk_labels
        self.risk_label_ids = risk_label_ids
        self.provider = provider
        self.raw_data = raw_data

    def __to_dict__(self) -> dict:
        """Return the risk-check result as a dictionary."""
        return {
            "check_result": self.check_result,
            "risk_labels": self.risk_labels,
            "risk_label_ids": self.risk_label_ids,
            "provider": self.provider,
        }

    def __json__(self) -> dict:
        """Return the risk-check result as JSON-compatible data."""
        return self.__to_dict__()
