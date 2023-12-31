import re


def correction_number(number: str) -> int:
    """
    :return: Returns int(number) if validation passed, returns 0 (False) if validation failed.
    """
    if not number or not re.match(r"^(?!0$)(?=.*\d)(?!0\d)\d{0,14}$", number):
        return 0
    else:
        return int(number)
