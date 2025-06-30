from objprint import op
import pprint
from typing import Any


# from .test_utils import dump
# dump(data)


# python -m pytest tests/test_xxx.py::xxx -v -s --disable-warnings
def dump(data: Any) -> None:
    print("\n=== Test Result ===")

    # Use objprint to display object structure
    print("--- Object Structure (objprint) ---")
    op(data, depth=10, width=120, elements=100)

    # If it's a dictionary type, use pprint to format display
    if isinstance(data, dict):
        print("\n--- Dictionary Content (pprint) ---")
        pp = pprint.PrettyPrinter(indent=2, depth=10, width=120)
        pp.pprint(data)

    # If it's a list type, also use pprint to format display
    elif isinstance(data, list):
        print("\n--- List Content (pprint) ---")
        pp = pprint.PrettyPrinter(indent=2, depth=10, width=120)
        pp.pprint(data)

    # If it's a SQLAlchemy model object or contains model objects
    elif hasattr(data, "__dict__") or (
        isinstance(data, dict)
        and any(hasattr(v, "__dict__") for v in data.values() if v is not None)
    ):
        print("\n--- Object Details ---")
        _dump_object_details(data)

    print("=================\n")


def _dump_object_details(obj: Any, max_depth: int = 3, current_depth: int = 0) -> None:
    """
    Recursively display detailed information of objects
    """
    if current_depth >= max_depth:
        print("  " * current_depth + "... (reached max depth)")
        return

    if isinstance(obj, dict):
        for key, value in obj.items():
            print("  " * current_depth + f"{key}:")
            if hasattr(value, "__dict__") and not isinstance(
                value, (str, int, float, bool, type(None))
            ):
                _dump_object_details(value, max_depth, current_depth + 1)
            else:
                print("  " * (current_depth + 1) + f"{value}")

    elif hasattr(obj, "__dict__"):
        # For SQLAlchemy model objects
        for attr_name in dir(obj):
            if not attr_name.startswith("_") and not callable(getattr(obj, attr_name)):
                try:
                    attr_value = getattr(obj, attr_name)
                    print("  " * current_depth + f"{attr_name}: {attr_value}")
                except Exception as e:
                    print(
                        "  " * current_depth + f"{attr_name}: <cannot get value: {e}>"
                    )


def dump_detailed(data: Any, include_methods: bool = False) -> None:
    """
    More detailed dump function, can choose whether to display methods
    """
    print("\n=== Detailed Test Result ===")

    if isinstance(data, dict):
        print("Data type: Dictionary")
        for key, value in data.items():
            print(f"\n--- Key: {key} ---")
            if hasattr(value, "__dict__"):
                print(f"Object type: {type(value).__name__}")
                _dump_object_attributes(value, include_methods)
            else:
                print(f"Value: {value}")

    elif hasattr(data, "__dict__"):
        print(f"Data type: {type(data).__name__}")
        _dump_object_attributes(data, include_methods)

    else:
        print(f"Data type: {type(data)}")
        print(f"Value: {data}")

    print("==================\n")


def _dump_object_attributes(obj: Any, include_methods: bool = False) -> None:
    """
    Display all attributes and optional methods of an object
    """
    print("Attributes:")
    for attr_name in dir(obj):
        if not attr_name.startswith("_"):
            try:
                attr_value = getattr(obj, attr_name)
                if not callable(attr_value):
                    print(f"  {attr_name}: {attr_value}")
                elif include_methods:
                    print(f"  {attr_name}: <method>")
            except Exception as e:
                print(f"  {attr_name}: <cannot access: {e}>")
