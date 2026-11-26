"""Campus Catalyst launcher. Starts the graphical app by default.
Use: python main.py --cli to launch the terminal version.
"""
import sys


def main():
    if "--cli" in sys.argv:
        from campus_catalyst.cli import run
        run()
        return
    try:
        import tkinter  # noqa: F401  (only checking that it is installed)
    except ImportError:
        print("Tkinter is not available (on some Linux systems install python3-tk).")
        print("Starting the terminal version instead.\n")
        from campus_catalyst.cli import run
        run()
        return
    from campus_catalyst.gui import run_gui
    run_gui()


if __name__ == "__main__":
    main()
