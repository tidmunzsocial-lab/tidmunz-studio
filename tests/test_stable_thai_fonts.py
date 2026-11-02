"""Real Tk checks for consistent defaults without changing intentional code/emoji fonts."""
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
import snapgen_fonts


def check_fonts():
    import tkinter as tk
    import tkinter.font as font
    root = tk.Tk()
    root.withdraw()
    try:
        default = tk.Label(root, text="ภาษาไทย")
        invalid_tuple = tk.Label(root, text="ภาษาไทย", font=("TkDefaultFont", 11, "bold"))
        code = tk.Text(root, font=("Consolas", 10))
        snapgen_fonts.apply_to_widget_tree(root)
        assert font.Font(root, font=default.cget("font")).actual("family") == "Tahoma"
        repaired = font.Font(root, font=invalid_tuple.cget("font"))
        assert repaired.actual("family") == "Tahoma" and repaired.actual("size") == 11
        assert repaired.actual("weight") == "bold"
        assert font.Font(root, font=code.cget("font")).actual("family") == "Consolas"
    finally:
        root.destroy()


def test_named_default_and_invalid_family_tuple_use_tahoma():
    # Tk stays in its own process; later API tests use worker threads.
    result = subprocess.run([sys.executable, "-B", __file__], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == "__main__":
    check_fonts()
