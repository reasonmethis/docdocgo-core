class ConditionalLogger:
    def __init__(self, verbose=True):
        self.verbose = verbose

    def log(self, message):
        if self.verbose:
            print(message)

    def log_no_newline(self, message):
        if self.verbose:
            print(message, end="")

    def log_error(self, message):
        print(message)


def format_exception(e: Exception) -> str:
    """
    Format an exception to include both its type and message.

    Args:
    e (Exception): The exception to be formatted.

    Returns:
    str: A string representation of the exception, including its type and message.

    Example:
        try:
            raise ValueError("An example error")
        except ValueError as e:
            formatted_exception = format_exception(e)
            print(formatted_exception)  # Output: "ValueError: An example error"
    """
    try:
        return f"{type(e).__name__}: {e}"
    except Exception:
        return f"Unknown error: {e}"

