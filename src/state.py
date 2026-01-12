"""
State management to track posted filings and prevent duplicates.
"""

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class PostState:
    """Tracks the last posted filing."""
    accession_number: str
    report_date: str
    posted_at: str
    tweet_ids: list[str]


class StateManager:
    """Manages state to prevent duplicate posts."""

    DEFAULT_STATE_FILE = ".gavin-baker-state.json"

    def __init__(self, state_file: Optional[str] = None):
        """
        Initialize state manager.

        Args:
            state_file: Path to state file (default: .gavin-baker-state.json in cwd)
        """
        self.state_file = Path(state_file or self.DEFAULT_STATE_FILE)

    def get_last_posted(self) -> Optional[PostState]:
        """Get the last posted filing state."""
        if not self.state_file.exists():
            return None

        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)
                return PostState(**data)
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def save_posted(self, accession_number: str, report_date: str, tweet_ids: list[str]) -> None:
        """
        Save the posted filing state.

        Args:
            accession_number: SEC accession number of the filing
            report_date: Quarter-end date of the filing
            tweet_ids: List of tweet IDs posted
        """
        state = PostState(
            accession_number=accession_number,
            report_date=report_date,
            posted_at=datetime.now().isoformat(),
            tweet_ids=tweet_ids,
        )

        with open(self.state_file, "w") as f:
            json.dump(asdict(state), f, indent=2)

    def is_already_posted(self, accession_number: str) -> bool:
        """
        Check if a filing has already been posted.

        Args:
            accession_number: SEC accession number to check

        Returns:
            True if already posted, False otherwise
        """
        last = self.get_last_posted()
        if last is None:
            return False
        return last.accession_number == accession_number

    def clear(self) -> None:
        """Clear the state file (useful for testing)."""
        if self.state_file.exists():
            self.state_file.unlink()
