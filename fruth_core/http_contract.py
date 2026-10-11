"""Public Fruth HTTP action marker shared by declared native callers."""

HTTP_ACTION_HEADER = 'X-Fruth-Action'
HTTP_ACTION_VALUE = '1'


def action_headers() -> dict[str, str]:
    """Declare an intentional API action; this is not native-process authentication."""
    return {HTTP_ACTION_HEADER: HTTP_ACTION_VALUE}
