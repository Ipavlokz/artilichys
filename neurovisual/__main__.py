from .cli import main

# Required for multiprocessing spawn on Windows: child imports must not run CLI.
if __name__ == "__main__":
    raise SystemExit(main())
