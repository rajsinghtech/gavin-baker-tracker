"""
X.com (Twitter) posting module using Tweepy.
"""

import os
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

        # Header tweet
        value_b = changes.current_total_value / 1_000_000_000
        change_pct = changes.total_value_change_pct
        change_sign = "+" if change_pct >= 0 else ""

        header = (
            f"🚨 Gavin Baker's Atreides Management 13F Update\n\n"
            f"📊 Q{self._get_quarter(changes.current_date)} Portfolio: ${value_b:.2f}B\n"
            f"📈 Change: {change_sign}{change_pct:.1f}%\n\n"
            f"🔄 {changes.num_changes} position changes\n"
            f"Thread 🧵👇"
        )
        tweets.append(header)

        # New positions tweet
        if changes.new_positions:
            new_tweet = "🆕 NEW POSITIONS:\n\n"
            for pos in changes.new_positions[:5]:
                value_m = pos.current_value / 1_000_000
                new_tweet += f"• ${pos.issuer[:20]} - ${value_m:.1f}M\n"
            if len(changes.new_positions) > 5:
                new_tweet += f"\n+{len(changes.new_positions) - 5} more..."
            tweets.append(new_tweet.strip())

        # Increased positions tweet
        if changes.increased_positions:
            inc_tweet = "📈 ADDED TO:\n\n"
            for pos in changes.increased_positions[:5]:
                inc_tweet += f"• ${pos.issuer[:20]} +{pos.share_change_pct:.0f}%\n"
            if len(changes.increased_positions) > 5:
                inc_tweet += f"\n+{len(changes.increased_positions) - 5} more..."
            tweets.append(inc_tweet.strip())

        # Decreased positions tweet
        if changes.decreased_positions:
            dec_tweet = "📉 TRIMMED:\n\n"
            for pos in changes.decreased_positions[:5]:
                dec_tweet += f"• ${pos.issuer[:20]} {pos.share_change_pct:.0f}%\n"
            if len(changes.decreased_positions) > 5:
                dec_tweet += f"\n+{len(changes.decreased_positions) - 5} more..."
            tweets.append(dec_tweet.strip())

        # Closed positions tweet
        if changes.closed_positions:
            closed_tweet = "🚪 EXITED:\n\n"
            for pos in changes.closed_positions[:5]:
                value_m = pos.previous_value / 1_000_000
                closed_tweet += f"• ${pos.issuer[:20]} (was ${value_m:.1f}M)\n"
            if len(changes.closed_positions) > 5:
                closed_tweet += f"\n+{len(changes.closed_positions) - 5} more..."
            tweets.append(closed_tweet.strip())

        # Footer tweet
        footer = (
            f"📅 Data from SEC 13F filing ({changes.current_date})\n\n"
            f"⚠️ 13F shows positions as of quarter-end. "
            f"Current holdings may differ.\n\n"
            f"🔗 Source: SEC EDGAR\n"
            f"#investing #hedgefunds #13F"
        )
        tweets.append(footer)

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

    def format_single_tweet(self, changes: PortfolioChanges) -> str:
        """
        Format portfolio changes into a single tweet (for simpler updates).

        Args:
            changes: Portfolio changes

        Returns:
            Formatted tweet string
        """
        value_b = changes.current_total_value / 1_000_000_000
        change_pct = changes.total_value_change_pct
        change_sign = "+" if change_pct >= 0 else ""

        tweet = (
            f"🚨 Atreides 13F Update (Q{self._get_quarter(changes.current_date)})\n\n"
            f"💰 ${value_b:.2f}B ({change_sign}{change_pct:.1f}%)\n"
        )

        # Add top moves
        top_buy = changes.get_top_buys(1)
        top_sell = changes.get_top_sells(1)

        if top_buy:
            pos = top_buy[0]
            if pos.change_type == "new":
                tweet += f"📈 New: ${pos.issuer[:15]}\n"
            else:
                tweet += f"📈 Added: ${pos.issuer[:15]} +{pos.share_change_pct:.0f}%\n"

        if top_sell:
            pos = top_sell[0]
            if pos.change_type == "closed":
                tweet += f"📉 Exit: ${pos.issuer[:15]}\n"
            else:
                tweet += f"📉 Trim: ${pos.issuer[:15]} {pos.share_change_pct:.0f}%\n"

        tweet += f"\n🔄 {changes.num_changes} total changes"

        return tweet


class DryRunPoster:
    """Mock poster for testing without actually posting to Twitter."""

    def __init__(self):
        pass

    def post_tweet(self, text: str, reply_to: Optional[str] = None) -> str:
        print(f"\n{'='*50}")
        print(f"[DRY RUN] Would post tweet:")
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
            print(f"\n--- Tweet {i}/{len(tweets)} ---")
            print(tweet)
            tweet_ids.append(f"dry_run_{i}")

        print("\n" + "="*60)
        return tweet_ids

    def format_single_tweet(self, changes: PortfolioChanges) -> str:
        poster = TwitterPoster.__new__(TwitterPoster)
        return poster.format_single_tweet(changes)
