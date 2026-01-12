"""
Portfolio comparison and change detection.
"""

from dataclasses import dataclass, field
from typing import Optional
from src.fetcher.edgar import Filing, Holding


@dataclass
class PositionChange:
    """Represents a change in a single position."""
    issuer: str
    cusip: str
    title: str
    current_shares: int
    previous_shares: int
    current_value: int  # in USD
    previous_value: int  # in USD
    current_weight: float  # portfolio weight (0-100%)
    previous_weight: float  # portfolio weight (0-100%)
    change_type: str  # 'new', 'closed', 'increased', 'decreased', 'unchanged'

    @property
    def share_change(self) -> int:
        """Absolute change in shares."""
        return self.current_shares - self.previous_shares

    @property
    def share_change_pct(self) -> float:
        """Percentage change in shares."""
        if self.previous_shares == 0:
            return 100.0 if self.current_shares > 0 else 0.0
        return (self.share_change / self.previous_shares) * 100

    @property
    def value_change(self) -> int:
        """Absolute change in value (USD)."""
        return self.current_value - self.previous_value

    @property
    def value_change_pct(self) -> float:
        """Percentage change in value."""
        if self.previous_value == 0:
            return 100.0 if self.current_value > 0 else 0.0
        return (self.value_change / self.previous_value) * 100

    @property
    def weight_change(self) -> float:
        """Change in portfolio weight (percentage points)."""
        return self.current_weight - self.previous_weight


@dataclass
class PortfolioChanges:
    """Summary of all portfolio changes between two filings."""
    current_date: str
    previous_date: str
    current_total_value: int
    previous_total_value: int
    new_positions: list[PositionChange] = field(default_factory=list)
    closed_positions: list[PositionChange] = field(default_factory=list)
    increased_positions: list[PositionChange] = field(default_factory=list)
    decreased_positions: list[PositionChange] = field(default_factory=list)
    unchanged_positions: list[PositionChange] = field(default_factory=list)

    @property
    def total_value_change(self) -> int:
        """Total portfolio value change in USD."""
        return self.current_total_value - self.previous_total_value

    @property
    def total_value_change_pct(self) -> float:
        """Total portfolio value change percentage."""
        if self.previous_total_value == 0:
            return 0.0
        return (self.total_value_change / self.previous_total_value) * 100

    @property
    def has_changes(self) -> bool:
        """Whether there are any portfolio changes."""
        return bool(
            self.new_positions
            or self.closed_positions
            or self.increased_positions
            or self.decreased_positions
        )

    @property
    def num_changes(self) -> int:
        """Total number of position changes."""
        return (
            len(self.new_positions)
            + len(self.closed_positions)
            + len(self.increased_positions)
            + len(self.decreased_positions)
        )

    def get_top_buys(self, n: int = 5) -> list[PositionChange]:
        """Get top N new or increased positions by weight change."""
        all_buys = self.new_positions + self.increased_positions
        return sorted(all_buys, key=lambda x: x.weight_change, reverse=True)[:n]

    def get_top_sells(self, n: int = 5) -> list[PositionChange]:
        """Get top N closed or decreased positions by weight change."""
        all_sells = self.closed_positions + self.decreased_positions
        return sorted(all_sells, key=lambda x: abs(x.weight_change), reverse=True)[:n]

    def get_top_positions(self, n: int = 10) -> list[PositionChange]:
        """Get top N positions by current portfolio weight."""
        all_positions = (
            self.new_positions
            + self.increased_positions
            + self.decreased_positions
            + self.unchanged_positions
        )
        return sorted(all_positions, key=lambda x: x.current_weight, reverse=True)[:n]


class PortfolioAnalyzer:
    """Analyzes changes between 13F filings."""

    def __init__(self, significance_threshold: float = 0.5):
        """
        Initialize the analyzer.

        Args:
            significance_threshold: Minimum weight change (in percentage points) to consider significant (default 0.5%)
        """
        self.significance_threshold = significance_threshold

    def compare(self, current: Filing, previous: Filing) -> PortfolioChanges:
        """
        Compare two filings and identify changes.

        Args:
            current: The more recent filing
            previous: The older filing

        Returns:
            PortfolioChanges object with all detected changes
        """
        changes = PortfolioChanges(
            current_date=current.report_date or current.filed_date,
            previous_date=previous.report_date or previous.filed_date,
            current_total_value=current.total_value,
            previous_total_value=previous.total_value,
        )

        # Build lookup dictionaries by CUSIP
        current_by_cusip = {h.cusip: h for h in current.holdings}
        previous_by_cusip = {h.cusip: h for h in previous.holdings}

        all_cusips = set(current_by_cusip.keys()) | set(previous_by_cusip.keys())

        for cusip in all_cusips:
            curr_holding = current_by_cusip.get(cusip)
            prev_holding = previous_by_cusip.get(cusip)

            change = self._analyze_position(
                curr_holding,
                prev_holding,
                current.total_value,
                previous.total_value,
            )

            if change.change_type == "new":
                changes.new_positions.append(change)
            elif change.change_type == "closed":
                changes.closed_positions.append(change)
            elif change.change_type == "increased":
                changes.increased_positions.append(change)
            elif change.change_type == "decreased":
                changes.decreased_positions.append(change)
            else:
                changes.unchanged_positions.append(change)

        # Sort by weight change
        changes.new_positions.sort(key=lambda x: x.current_weight, reverse=True)
        changes.closed_positions.sort(key=lambda x: x.previous_weight, reverse=True)
        changes.increased_positions.sort(key=lambda x: x.weight_change, reverse=True)
        changes.decreased_positions.sort(key=lambda x: abs(x.weight_change), reverse=True)

        return changes

    def _analyze_position(
        self,
        current: Optional[Holding],
        previous: Optional[Holding],
        current_total: int,
        previous_total: int,
    ) -> PositionChange:
        """Analyze change for a single position."""

        if current is None and previous is None:
            raise ValueError("Both holdings cannot be None")

        # Calculate portfolio weights
        def calc_weight(value: int, total: int) -> float:
            if total == 0:
                return 0.0
            return (value / total) * 100

        if current is None:
            # Position was closed
            prev_weight = calc_weight(previous.value_usd, previous_total)
            return PositionChange(
                issuer=previous.issuer,
                cusip=previous.cusip,
                title=previous.title,
                current_shares=0,
                previous_shares=previous.shares,
                current_value=0,
                previous_value=previous.value_usd,
                current_weight=0.0,
                previous_weight=prev_weight,
                change_type="closed",
            )

        if previous is None:
            # New position
            curr_weight = calc_weight(current.value_usd, current_total)
            return PositionChange(
                issuer=current.issuer,
                cusip=current.cusip,
                title=current.title,
                current_shares=current.shares,
                previous_shares=0,
                current_value=current.value_usd,
                previous_value=0,
                current_weight=curr_weight,
                previous_weight=0.0,
                change_type="new",
            )

        # Position exists in both - check for changes
        curr_weight = calc_weight(current.value_usd, current_total)
        prev_weight = calc_weight(previous.value_usd, previous_total)
        weight_change = curr_weight - prev_weight

        if weight_change > self.significance_threshold:
            change_type = "increased"
        elif weight_change < -self.significance_threshold:
            change_type = "decreased"
        else:
            change_type = "unchanged"

        return PositionChange(
            issuer=current.issuer,
            cusip=current.cusip,
            title=current.title,
            current_shares=current.shares,
            previous_shares=previous.shares,
            current_value=current.value_usd,
            previous_value=previous.value_usd,
            current_weight=curr_weight,
            previous_weight=prev_weight,
            change_type=change_type,
        )

    def generate_summary(self, changes: PortfolioChanges) -> str:
        """Generate a human-readable summary of portfolio changes."""
        lines = []

        lines.append(f"Portfolio Changes: {changes.previous_date} → {changes.current_date}")
        lines.append("=" * 60)

        # Overall stats
        value_b = changes.current_total_value / 1_000_000_000
        lines.append(f"\nTotal Value: ${value_b:.2f}B")
        change_sign = "+" if changes.total_value_change >= 0 else ""
        lines.append(
            f"Change: {change_sign}{changes.total_value_change_pct:.1f}%"
        )

        lines.append(f"\nPosition Changes: {changes.num_changes}")
        lines.append(f"  - New Positions: {len(changes.new_positions)}")
        lines.append(f"  - Closed Positions: {len(changes.closed_positions)}")
        lines.append(f"  - Weight Increased: {len(changes.increased_positions)}")
        lines.append(f"  - Weight Decreased: {len(changes.decreased_positions)}")

        # Top positions by current weight
        lines.append("\n📊 TOP HOLDINGS (by portfolio %):")
        for pos in changes.get_top_positions(10):
            weight_delta = f"+{pos.weight_change:.1f}pp" if pos.weight_change > 0 else f"{pos.weight_change:.1f}pp"
            lines.append(f"  {pos.current_weight:5.1f}% | {pos.issuer[:30]:<30} ({weight_delta})")

        # Top buys by weight change
        if changes.new_positions or changes.increased_positions:
            lines.append("\n📈 BIGGEST WEIGHT INCREASES:")
            for pos in changes.get_top_buys(5):
                if pos.change_type == "new":
                    lines.append(f"  +{pos.current_weight:.1f}pp | {pos.issuer} (NEW)")
                else:
                    lines.append(
                        f"  +{pos.weight_change:.1f}pp | {pos.issuer} "
                        f"({pos.previous_weight:.1f}% → {pos.current_weight:.1f}%)"
                    )

        # Top sells by weight change
        if changes.closed_positions or changes.decreased_positions:
            lines.append("\n📉 BIGGEST WEIGHT DECREASES:")
            for pos in changes.get_top_sells(5):
                if pos.change_type == "closed":
                    lines.append(f"  -{pos.previous_weight:.1f}pp | {pos.issuer} (EXITED)")
                else:
                    lines.append(
                        f"  {pos.weight_change:.1f}pp | {pos.issuer} "
                        f"({pos.previous_weight:.1f}% → {pos.current_weight:.1f}%)"
                    )

        return "\n".join(lines)
