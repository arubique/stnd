import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--long_flag", action="store_true")
    parser.add_argument("-s", action="store_true")
    parser.add_argument("--user_number", type=int, required=True)
    args = parser.parse_args()

    if args.long_flag and args.s:
        print(f"answer: {42 + args.user_number}")

    return 0


if __name__ == "__main__":
    main()
