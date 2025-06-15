import sys
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--print_stdout", action="store_true")
    parser.add_argument("-p", action="store_true")
    parser.add_argument("--number_arg", type=int, required=True)
    args = parser.parse_args()
    assert args.number_arg == 10
    if args.print_stdout:
        print("Hello, stdout")
        print("save_number: 10.0")
        print("save_number: 12.0")

    if args.p:
        print("save_number: 13.0")
        print("Hello, stderr", file=sys.stderr)
    return 0


if __name__ == "__main__":
    main()
