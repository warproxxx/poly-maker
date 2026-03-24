import sys

from tweet_engine.cli import main


if __name__ == "__main__":
    main(["replay_tweet_strategies", *sys.argv[1:]])
