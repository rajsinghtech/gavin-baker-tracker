#!/usr/bin/env python3
"""
Gavin Baker Portfolio Tracker

Fetches the latest 13F filing from SEC EDGAR for Atreides Management,
compares it to the previous quarter, and posts updates to X.com.
"""

import argparse
import os
import sys
from datetime import datetime

from src.fetcher import EdgarClient
from src.analyzer import PortfolioAnalyzer
from src.poster.twitter import TwitterPoster, DryRunPoster
from src.state import StateManager


def main():
    parser = argparse.ArgumentParser(
        description="Track Gavin Baker's Atreides Management portfolio and post to X.com"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print tweets without posting to X.com",
    )
    parser.add_argument(
        "--single-tweet",
        action="store_true",
        help="Post a single tweet instead of a thread",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print portfolio summary without posting",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force posting even if already posted this filing",
    )
    parser.add_argument(
        "--user-agent",
        default=os.environ.get("SEC_USER_AGENT", "GavinBakerTracker contact@example.com"),
        help="User agent for SEC EDGAR requests (required by SEC)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.05,
        help="Significance threshold for position changes (default: 0.05 = 5%%)",
    )
    parser.add_argument(
        "--state-file",
        default=None,
        help="Path to state file for tracking posted filings",
    )

    args = parser.parse_args()

    print(f"[{datetime.now().isoformat()}] Starting Gavin Baker Portfolio Tracker")
    print("=" * 60)

    # Initialize clients
    edgar = EdgarClient(user_agent=args.user_agent)
    analyzer = PortfolioAnalyzer(significance_threshold=args.threshold)
    state = StateManager(state_file=args.state_file)

    # Fetch filings
    print("\n📥 Fetching 13F filings from SEC EDGAR...")
    try:
        current, previous = edgar.get_last_two_filings()
        print(f"   Current filing: {current.filed_date} ({current.num_positions} positions)")
        print(f"   Previous filing: {previous.filed_date} ({previous.num_positions} positions)")
        print(f"   Accession: {current.accession_number}")
    except Exception as e:
        print(f"❌ Error fetching filings: {e}")
        sys.exit(1)

    # Check if already posted
    if not args.dry_run and not args.summary_only and not args.force:
        if state.is_already_posted(current.accession_number):
            last = state.get_last_posted()
            print(f"\n⏭️  Already posted this filing!")
            print(f"   Accession: {current.accession_number}")
            print(f"   Posted at: {last.posted_at}")
            print(f"   Tweet: https://x.com/i/status/{last.tweet_ids[0]}")
            print("\n   Use --force to post again.")
            sys.exit(0)

    # Analyze changes
    print("\n🔍 Analyzing portfolio changes...")
    changes = analyzer.compare(current, previous)

    if not changes.has_changes:
        print("   No significant changes detected.")
        if not args.summary_only:
            print("   Skipping tweet.")
        sys.exit(0)

    # Print summary
    print("\n" + analyzer.generate_summary(changes))

    if args.summary_only:
        sys.exit(0)

    # Post to Twitter
    print("\n📤 Posting to X.com...")

    if args.dry_run:
        poster = DryRunPoster()
    else:
        try:
            poster = TwitterPoster()
        except ValueError as e:
            print(f"❌ {e}")
            print("   Use --dry-run to test without posting.")
            sys.exit(1)

    try:
        if args.single_tweet:
            tweet_text = poster.format_single_tweet(changes)
            if args.dry_run:
                poster.post_tweet(tweet_text)
            else:
                tweet_id = poster.post_tweet(tweet_text)
                print(f"✅ Posted tweet: https://x.com/i/status/{tweet_id}")
                # Save state
                state.save_posted(
                    accession_number=current.accession_number,
                    report_date=changes.current_date,
                    tweet_ids=[tweet_id],
                )
        else:
            tweet_ids = poster.post_portfolio_update(changes)
            if not args.dry_run:
                print(f"✅ Posted thread with {len(tweet_ids)} tweets")
                print(f"   First tweet: https://x.com/i/status/{tweet_ids[0]}")
                # Save state
                state.save_posted(
                    accession_number=current.accession_number,
                    report_date=changes.current_date,
                    tweet_ids=tweet_ids,
                )
    except Exception as e:
        print(f"❌ Error posting to X.com: {e}")
        sys.exit(1)

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
