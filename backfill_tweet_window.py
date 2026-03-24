import sys

from tweet_engine.cli import main


if __name__ == "__main__":
    main(["backfill_tweet_window", *sys.argv[1:]])
