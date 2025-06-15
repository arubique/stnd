import sys


def main():
    print("Hello, stdout")
    print("Hello, stderr", file=sys.stderr)
    return 0


if __name__ == "__main__":
    main()
