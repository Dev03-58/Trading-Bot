import sys

def verify():
    all_passed = True
    print("Checking dependencies...")

    packages = [
        ("ccxt", "ccxt"),
        ("pandas", "pandas"),
        ("pandas-ta", "pandas_ta"),
        ("python-dotenv", "dotenv"),
        ("requests", "requests"),
    ]

    for display_name, import_name in packages:
        try:
            mod = __import__(import_name)
            version = getattr(mod, "__version__", "installed")
            print(f"  [OK]   {display_name} ({version})")
        except ImportError as e:
            print(f"  [FAIL] {display_name}: {e}")
            all_passed = False

    print("\nLoading configuration...")
    try:
        import config
        print(f"  [OK]   config.py loaded successfully")
        print(f"         SYMBOL      : {config.SYMBOL}")
        print(f"         TIMEFRAME   : {config.TIMEFRAME}")
        print(f"         USE_TESTNET : {config.USE_TESTNET}")
    except Exception as e:
        print(f"  [FAIL] Failed to load config.py: {e}")
        all_passed = False

    print("\n" + "=" * 40)
    if all_passed:
        print("SETUP COMPLETE")
        print("=" * 40)
        sys.exit(0)
    else:
        print("SETUP INCOMPLETE: Some checks failed.")
        print("=" * 40)
        sys.exit(1)

if __name__ == "__main__":
    verify()
