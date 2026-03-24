import sys

from tweet_engine.cli import main


if __name__ == "__main__":
    main(["record_tweet_markets", *sys.argv[1:]])
