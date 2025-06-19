import decimal


def compare_decimal(a, b):
    a_temp = decimal.Decimal(str(a if a else 0)).quantize(
        decimal.Decimal("0.01"), rounding=decimal.ROUND_DOWN
    )
    b_temp = decimal.Decimal(str(b if b else 0)).quantize(
        decimal.Decimal("0.01"), rounding=decimal.ROUND_DOWN
    )
    return a_temp == b_temp


def compare_str(a, b):
    a_str = str(a if a else "")
    b_str = str(b if b else "")
    return a_str == b_str
