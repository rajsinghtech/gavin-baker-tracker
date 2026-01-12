"""
X.com (Twitter) posting module using Tweepy.
"""

import os
from datetime import datetime
import tweepy
from typing import Optional
from src.analyzer.compare import PortfolioChanges, PositionChange


class TwitterPoster:
    """Posts portfolio updates to X.com (Twitter)."""

    MAX_TWEET_LENGTH = 280
    THREAD_DELAY = 1  # seconds between tweets in a thread

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        access_secret: Optional[str] = None,
    ):
        """
        Initialize the Twitter poster.

        Credentials can be passed directly or loaded from environment variables:
        - TWITTER_API_KEY
        - TWITTER_API_SECRET
        - TWITTER_ACCESS_TOKEN
        - TWITTER_ACCESS_SECRET
        """
        self.api_key = api_key or os.environ.get("TWITTER_API_KEY")
        self.api_secret = api_secret or os.environ.get("TWITTER_API_SECRET")
        self.access_token = access_token or os.environ.get("TWITTER_ACCESS_TOKEN")
        self.access_secret = access_secret or os.environ.get("TWITTER_ACCESS_SECRET")

        if not all([self.api_key, self.api_secret, self.access_token, self.access_secret]):
            raise ValueError(
                "Twitter credentials required. Set TWITTER_API_KEY, TWITTER_API_SECRET, "
                "TWITTER_ACCESS_TOKEN, and TWITTER_ACCESS_SECRET environment variables."
            )

        self.client = tweepy.Client(
            consumer_key=self.api_key,
            consumer_secret=self.api_secret,
            access_token=self.access_token,
            access_token_secret=self.access_secret,
        )

    def post_tweet(self, text: str, reply_to: Optional[str] = None) -> str:
        """
        Post a single tweet.

        Args:
            text: Tweet content (max 280 characters)
            reply_to: Optional tweet ID to reply to (for threads)

        Returns:
            Tweet ID of the posted tweet
        """
        if len(text) > self.MAX_TWEET_LENGTH:
            raise ValueError(f"Tweet exceeds {self.MAX_TWEET_LENGTH} characters: {len(text)}")

        response = self.client.create_tweet(
            text=text,
            in_reply_to_tweet_id=reply_to,
        )
        return response.data["id"]

    def post_portfolio_update(self, changes: PortfolioChanges) -> list[str]:
        """
        Post a portfolio update as a thread.

        Args:
            changes: Portfolio changes to post

        Returns:
            List of tweet IDs in the thread
        """
        tweets = self._format_thread(changes)
        tweet_ids = []

        reply_to = None
        for tweet in tweets:
            tweet_id = self.post_tweet(tweet, reply_to=reply_to)
            tweet_ids.append(tweet_id)
            reply_to = tweet_id

        return tweet_ids

    def _format_thread(self, changes: PortfolioChanges) -> list[str]:
        """Format portfolio changes into a thread of tweets."""
        tweets = []

        value_b = changes.current_total_value / 1_000_000_000
        change_pct = changes.total_value_change_pct
        change_sign = "+" if change_pct >= 0 else ""
        date_formatted = self._format_date(changes.current_date)

        # Tweet 1: Header with top holdings
        top_holdings = changes.get_top_positions(5)
        header = f"Gavin Baker 13F ({date_formatted})\n\n"
        header += f"AUM: ${value_b:.2f}B ({change_sign}{change_pct:.1f}%)\n\n"
        header += "Top Holdings:\n"
        for pos in top_holdings:
            header += f"{pos.current_weight:.1f}% {pos.issuer[:20]}\n"
        tweets.append(header.strip())

        # Tweet 2: Buys
        top_buys = changes.get_top_buys(6)
        if top_buys:
            buys = "Bought:\n\n"
            for pos in top_buys:
                tag = " (new)" if pos.change_type == "new" else ""
                buys += f"+{pos.weight_change:.1f}% {pos.issuer[:22]}{tag}\n"
            tweets.append(buys.strip())

        # Tweet 3: Sells
        top_sells = changes.get_top_sells(6)
        if top_sells:
            sells = "Sold:\n\n"
            for pos in top_sells:
                tag = " (exit)" if pos.change_type == "closed" else ""
                sells += f"{pos.weight_change:.1f}% {pos.issuer[:22]}{tag}\n"
            tweets.append(sells.strip())

        return tweets

    def _get_quarter(self, date_str: str) -> str:
        """Extract quarter from date string (YYYY-MM-DD)."""
        if not date_str:
            return "?"
        try:
            month = int(date_str.split("-")[1])
            return str((month - 1) // 3 + 1)
        except (IndexError, ValueError):
            return "?"

    def _get_year(self, date_str: str) -> str:
        """Extract year from date string (YYYY-MM-DD)."""
        if not date_str:
            return ""
        try:
            return date_str.split("-")[0]
        except IndexError:
            return ""

    def _format_date(self, date_str: str) -> str:
        """Format date string (YYYY-MM-DD) to readable format like 'Sep 30th, 2025'."""
        if not date_str:
            return ""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            day = dt.day
            # Add ordinal suffix
            if 11 <= day <= 13:
                suffix = "th"
            else:
                suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
            return dt.strftime(f"%b {day}{suffix}, %Y")
        except ValueError:
            return date_str

    def _get_ticker(self, issuer: str) -> str:
        """Format issuer as $TICKER style."""
        # Take first word, clean it up
        first_word = issuer.split()[0] if issuer else "?"
        return f"${first_word.upper()}"

    def format_single_tweet(self, changes: PortfolioChanges) -> str:
        """Format portfolio changes into a single tweet."""
        value_b = changes.current_total_value / 1_000_000_000
        change_pct = changes.total_value_change_pct
        change_sign = "+" if change_pct >= 0 else ""
        date_formatted = self._format_date(changes.current_date)

        tweet = f"Gavin Baker 13F ({date_formatted})\n\n"
        tweet += f"AUM: ${value_b:.2f}B ({change_sign}{change_pct:.1f}%)\n\n"

        top_buy = changes.get_top_buys(1)
        top_sell = changes.get_top_sells(1)

        if top_buy:
            pos = top_buy[0]
            tag = " (new)" if pos.change_type == "new" else ""
            tweet += f"Top buy: {pos.issuer[:18]}  +{pos.weight_change:.1f}%{tag}\n"

        if top_sell:
            pos = top_sell[0]
            tag = " (exit)" if pos.change_type == "closed" else ""
            tweet += f"Top sell: {pos.issuer[:18]} {pos.weight_change:.1f}%{tag}"

        return tweet


class DryRunPoster:
    """Mock poster for testing without actually posting to Twitter."""

    def __init__(self):
        pass

    def post_tweet(self, text: str, reply_to: Optional[str] = None) -> str:
        print(f"\n{'='*50}")
        print(f"[DRY RUN] Would post tweet ({len(text)} chars):")
        print(f"{'='*50}")
        print(text)
        print(f"{'='*50}")
        if reply_to:
            print(f"(Reply to: {reply_to})")
        return f"dry_run_{hash(text)}"

    def post_portfolio_update(self, changes: PortfolioChanges) -> list[str]:
        poster = TwitterPoster.__new__(TwitterPoster)
        tweets = poster._format_thread(changes)

        print("\n" + "="*60)
        print("[DRY RUN] Would post thread:")
        print("="*60)

        tweet_ids = []
        for i, tweet in enumerate(tweets, 1):
            print(f"\n--- Tweet {i}/{len(tweets)} ({len(tweet)} chars) ---")
            print(tweet)
            tweet_ids.append(f"dry_run_{i}")

        print("\n" + "="*60)
        return tweet_ids

    def format_single_tweet(self, changes: PortfolioChanges) -> str:
        poster = TwitterPoster.__new__(TwitterPoster)
        return poster.format_single_tweet(changes)
