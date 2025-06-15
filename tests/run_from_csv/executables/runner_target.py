import sys
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--print_stdout", action="store_true")
    parser.add_argument("-p", action="store_true")
    args = parser.parse_args()
    if args.print_stdout:
        print("Hello, stdout")
    if args.p:
        print("Hello, stderr", file=sys.stderr)
    return 0


if __name__ == "__main__":
    main()
