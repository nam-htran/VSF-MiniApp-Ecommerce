class VAppApiError(Exception):
    """A non-zero `code` from the Open API envelope.

    HTTP 200 with code != 0 is a failure, so this is raised from the
    envelope, not from the HTTP status.
    """

    def __init__(self, code: int, message: str, http_status: int) -> None:
        super().__init__(f"V-App API error {code}: {message}")
        self.code = code
        self.message = message
        self.http_status = http_status
