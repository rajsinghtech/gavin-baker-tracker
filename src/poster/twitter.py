"""
X.com (Twitter) posting module using Tweepy.
"""

import json
import os
from datetime import datetime
from pathlib import Path
import tweepy
from typing import Optional
from src.analyzer.compare import PortfolioChanges, PositionChange


class CUSIPResolver:
    """Resolves CUSIP numbers to ticker symbols using free SEC data."""

    CACHE_FILE = Path(__file__).parent.parent.parent / ".ticker_cache.json"

    def __init__(self):
        self._cache = self._load_cache()
        self._loaded_sources = False

    def _load_cache(self) -> dict[str, str]:
        """Load persistent cache from file."""
        if self.CACHE_FILE.exists():
            try:
                with open(self.CACHE_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_cache(self) -> None:
        """Save cache to file."""
        try:
            with open(self.CACHE_FILE, "w") as f:
                json.dump(self._cache, f, indent=2)
        except Exception:
            pass

    def _load_sources(self) -> None:
        """Load CUSIP data from free sources (lazy load)."""
        if self._loaded_sources:
            return

        import requests

        # Try SEC FTD data (has CUSIP -> Symbol mapping)
        try:
            # Get recent FTD file
            ftd_url = "https://www.sec.gov/files/data/fails-deliver-data/cnsfails202412b.zip"
            resp = requests.get(ftd_url, timeout=30)
            if resp.status_code == 200:
                import io
                import zipfile
                import csv

                with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                    for name in z.namelist():
                        if name.endswith('.txt'):
                            with z.open(name) as f:
                                reader = csv.DictReader(
                                    io.TextIOWrapper(f, encoding='utf-8'),
                                    delimiter='|'
                                )
                                for row in reader:
                                    cusip = row.get('CUSIP', '').strip()
                                    symbol = row.get('SYMBOL', '').strip()
                                    if cusip and symbol and cusip not in self._cache:
                                        self._cache[cusip] = symbol
        except Exception:
            pass

        # Try GitHub yoshishima dataset as backup
        try:
            csv_url = "https://raw.githubusercontent.com/yoshishima/Stock_Data/master/CUSIP.csv"
            resp = requests.get(csv_url, timeout=15)
            if resp.status_code == 200:
                import csv
                import io
                reader = csv.DictReader(io.StringIO(resp.text))
                for row in reader:
                    cusip = row.get('CUSIP', '').strip()
                    symbol = row.get('Symbol', '').strip()
                    if cusip and symbol and cusip not in self._cache:
                        self._cache[cusip] = symbol
        except Exception:
            pass

        self._loaded_sources = True
        self._save_cache()

    def resolve(self, cusip: str) -> str | None:
        """Resolve a CUSIP to ticker symbol."""
        if not cusip:
            return None

        # Check cache first
        if cusip in self._cache:
            return self._cache[cusip]

        # Try without check digit (8 chars)
        cusip8 = cusip[:8] if len(cusip) >= 8 else cusip
        if cusip8 in self._cache:
            return self._cache[cusip8]

        # Load sources if needed
        if not self._loaded_sources:
            self._load_sources()

            # Check again after loading
            if cusip in self._cache:
                return self._cache[cusip]
            if cusip8 in self._cache:
                return self._cache[cusip8]

        return None

    def resolve_batch(self, cusips: list[str]) -> dict[str, str | None]:
        """Resolve multiple CUSIPs at once."""
        # Ensure sources are loaded
        if not self._loaded_sources:
            self._load_sources()

        return {cusip: self.resolve(cusip) for cusip in cusips}


# Global resolver instance
_resolver = None

def get_resolver() -> CUSIPResolver:
    global _resolver
    if _resolver is None:
        _resolver = CUSIPResolver()
    return _resolver


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

        # Get top tickers for header
        top_buys = changes.get_top_buys(3)
        top_sells = changes.get_top_sells(3)

        buy_tickers = ", ".join([self._get_ticker(p.issuer, p.cusip) for p in top_buys])
        sell_tickers = ", ".join([self._get_ticker(p.issuer, p.cusip) for p in top_sells])

        date_formatted = self._format_date(changes.current_date)
        header = (
            f"🚨 Gavin Baker's Atreides 13F Update\n\n"
            f"📅 {date_formatted}\n"
            f"💰 ${value_b:.2f}B ({change_sign}{change_pct:.1f}%)\n\n"
            f"🟢 {buy_tickers}\n"
            f"🔴 {sell_tickers}"
        )
        tweets.append(header)

        # Top holdings tweet
        top_holdings = changes.get_top_positions(5)
        if top_holdings:
            holdings_tweet = "🏆 Top 5 Holdings:\n\n"
            for pos in top_holdings:
                delta = f"+{pos.weight_change:.1f}%" if pos.weight_change > 0 else f"{pos.weight_change:.1f}%"
                holdings_tweet += f"{pos.current_weight:.1f}% {self._get_ticker(pos.issuer, pos.cusip)} ({delta})\n"
            tweets.append(holdings_tweet.strip())

        # Purchases tweet
        top_buys = changes.get_top_buys(5)
        if top_buys:
            buys_tweet = "📈 Biggest Buys:\n\n"
            for pos in top_buys:
                if pos.change_type == "new":
                    buys_tweet += f"+{pos.current_weight:.1f}% {self._get_ticker(pos.issuer, pos.cusip)} 🆕\n"
                else:
                    buys_tweet += f"+{pos.weight_change:.1f}% {self._get_ticker(pos.issuer, pos.cusip)}\n"
            tweets.append(buys_tweet.strip())

        # Sales tweet
        top_sells = changes.get_top_sells(5)
        if top_sells:
            sells_tweet = "📉 Biggest Sells:\n\n"
            for pos in top_sells:
                if pos.change_type == "closed":
                    sells_tweet += f"-{pos.previous_weight:.1f}% {self._get_ticker(pos.issuer, pos.cusip)} 🚪\n"
                else:
                    sells_tweet += f"{pos.weight_change:.1f}% {self._get_ticker(pos.issuer, pos.cusip)}\n"
            tweets.append(sells_tweet.strip())

        # New positions tweet (if any beyond top buys)
        new_not_in_top = [p for p in changes.new_positions if p not in top_buys][:5]
        if new_not_in_top:
            new_tweet = "✨ Other New Positions:\n\n"
            for pos in new_not_in_top:
                new_tweet += f"{pos.current_weight:.1f}% {self._get_ticker(pos.issuer, pos.cusip)}\n"
            tweets.append(new_tweet.strip())

        # Exits tweet (if any beyond top sells)
        exits_not_in_top = [p for p in changes.closed_positions if p not in top_sells][:5]
        if exits_not_in_top:
            exits_tweet = "👋 Exits:\n\n"
            for pos in exits_not_in_top:
                exits_tweet += f"(was {pos.previous_weight:.1f}%) {self._get_ticker(pos.issuer, pos.cusip)}\n"
            tweets.append(exits_tweet.strip())

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

    def _get_ticker(self, issuer: str, cusip: str = "") -> str:
        """Get ticker from CUSIP using SEC data."""
        if not cusip and not issuer:
            return "$?"

        # Try resolver
        resolver = get_resolver()
        ticker = resolver.resolve(cusip)
        if ticker:
            return f"${ticker}"

        # Fallback: first word of issuer
        first_word = issuer.split()[0].upper() if issuer else "?"
        return f"${first_word}"

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
        date_formatted = self._format_date(changes.current_date)

        tweet = (
            f"Atreides 13F - {date_formatted}\n\n"
            f"AUM: ${value_b:.2f}B ({change_sign}{change_pct:.1f}%)\n\n"
        )

        # Add top move up and down
        top_buy = changes.get_top_buys(1)
        top_sell = changes.get_top_sells(1)

        if top_buy:
            pos = top_buy[0]
            if pos.change_type == "new":
                tweet += f"Top buy: {self._get_ticker(pos.issuer, pos.cusip)} +{pos.current_weight:.1f}% (NEW)\n"
            else:
                tweet += f"Top buy: {self._get_ticker(pos.issuer, pos.cusip)} +{pos.weight_change:.1f}%\n"

        if top_sell:
            pos = top_sell[0]
            if pos.change_type == "closed":
                tweet += f"Top sale: {self._get_ticker(pos.issuer, pos.cusip)} -{pos.previous_weight:.1f}% (EXIT)\n"
            else:
                tweet += f"Top sale: {self._get_ticker(pos.issuer, pos.cusip)} {pos.weight_change:.1f}%\n"

        tweet += f"\n{changes.num_changes} changes | SEC EDGAR"

        return tweet


class DryRunPoster(TwitterPoster):
    """Mock poster for testing without actually posting to Twitter."""

    def __init__(self):
        # Skip parent __init__ which requires credentials
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
        tweets = self._format_thread(changes)

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
