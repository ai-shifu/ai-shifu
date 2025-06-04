from objprint import op


# from .test_utils import dump
# dump(data)


# python -m pytest tests/test_xxx.py::xxx -v -s --disable-warnings
def dump(data: None) -> None:
    print("\n=== Test Result ===")
    op(data)
    print("=================\n")
