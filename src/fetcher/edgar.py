"""
SEC EDGAR API client for fetching 13F filings.
"""

import requests
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import time
import re


@dataclass
class Holding:
    """Represents a single holding in a 13F filing."""
    issuer: str
    title: str
    cusip: str
    value: int  # value in thousands USD (as reported in 13F)
    shares: int
    share_type: str  # SH or PRN
    put_call: Optional[str]  # Put, Call, or None
    investment_discretion: str
    voting_sole: int
    voting_shared: int
    voting_none: int

    @property
    def value_usd(self) -> int:
        """Value in actual USD."""
        # SEC 13F reports value in thousands, so multiply by 1000
        # But actual SEC XMLs appear to be in actual dollars already
        return self.value


@dataclass
class Filing:
    """Represents a 13F filing."""
    accession_number: str
    filed_date: str
    report_date: str
    form_type: str
    holdings: list[Holding]

    @property
    def total_value(self) -> int:
        """Total portfolio value in USD."""
        return sum(h.value_usd for h in self.holdings)

    @property
    def num_positions(self) -> int:
        """Number of positions in the portfolio."""
        return len(self.holdings)


class EdgarClient:
    """Client for fetching 13F filings from SEC EDGAR."""

    BASE_URL = "https://data.sec.gov"
    ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"

    # Atreides Management CIK
    ATREIDES_CIK = "0001777813"

    # XML namespaces used in 13F filings
    NS = {
        "ns1": "http://www.sec.gov/edgar/document/thirteenf/informationtable",
        "ns2": "http://www.sec.gov/edgar/thirteenfholdingsinfo"
    }

    def __init__(self, user_agent: str, cik: str = ATREIDES_CIK):
        """
        Initialize the EDGAR client.

        Args:
            user_agent: Required by SEC - format: "Name email@example.com"
            cik: Company CIK number (default: Atreides Management)
        """
        self.cik = cik.zfill(10)  # Pad to 10 digits
        self.headers = {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
        }
        self._rate_limit_delay = 0.1  # 10 requests/second max

    def _request(self, url: str) -> requests.Response:
        """Make a rate-limited request to SEC EDGAR."""
        time.sleep(self._rate_limit_delay)
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response

    def get_filing_history(self, limit: int = 8) -> list[dict]:
        """
        Get list of 13F filings for the company.

        Args:
            limit: Maximum number of filings to return

        Returns:
            List of filing metadata dicts
        """
        url = f"{self.BASE_URL}/submissions/CIK{self.cik}.json"
        response = self._request(url)
        data = response.json()

        filings = []
        recent = data.get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        report_dates = recent.get("reportDate", [])

        for i, form in enumerate(forms):
            if "13F" in form and len(filings) < limit:
                filings.append({
                    "form_type": form,
                    "filed_date": dates[i],
                    "accession_number": accessions[i],
                    "report_date": report_dates[i] if i < len(report_dates) else None,
                })

        return filings

    def get_filing(self, accession_number: str) -> Filing:
        """
        Fetch and parse a specific 13F filing.

        Args:
            accession_number: SEC accession number (e.g., "0001104659-24-012345")

        Returns:
            Parsed Filing object with holdings
        """
        # Get filing index to find the information table file
        acc_clean = accession_number.replace("-", "")
        cik_clean = self.cik.lstrip("0")

        index_url = f"{self.ARCHIVES_URL}/{cik_clean}/{acc_clean}/index.json"
        index_response = self._request(index_url)
        index_data = index_response.json()

        # Find the information table XML file
        info_table_file = None
        for item in index_data.get("directory", {}).get("item", []):
            name = item.get("name", "")
            if "infotable" in name.lower() and name.endswith(".xml"):
                info_table_file = name
                break

        if not info_table_file:
            # Try alternative naming patterns
            for item in index_data.get("directory", {}).get("item", []):
                name = item.get("name", "")
                if name.endswith(".xml") and "13f" in name.lower():
                    info_table_file = name
                    break

        if not info_table_file:
            raise ValueError(f"Could not find information table for filing {accession_number}")

        # Fetch and parse the information table
        table_url = f"{self.ARCHIVES_URL}/{cik_clean}/{acc_clean}/{info_table_file}"
        table_response = self._request(table_url)

        holdings = self._parse_info_table(table_response.text)

        # Get filing metadata
        filing_meta = None
        for f in self.get_filing_history(limit=20):
            if f["accession_number"] == accession_number:
                filing_meta = f
                break

        return Filing(
            accession_number=accession_number,
            filed_date=filing_meta["filed_date"] if filing_meta else "",
            report_date=filing_meta["report_date"] if filing_meta else "",
            form_type=filing_meta["form_type"] if filing_meta else "13F-HR",
            holdings=holdings,
        )

    def _parse_info_table(self, xml_content: str) -> list[Holding]:
        """Parse the 13F information table XML."""
        holdings = []

        # Try to parse with namespace
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            raise ValueError(f"Failed to parse XML: {e}")

        # Find all infoTable entries (try multiple namespace patterns)
        entries = root.findall(".//ns1:infoTable", self.NS)
        if not entries:
            entries = root.findall(".//{http://www.sec.gov/edgar/document/thirteenf/informationtable}infoTable")
        if not entries:
            # Try without namespace
            entries = root.findall(".//infoTable")

        for entry in entries:
            holding = self._parse_holding(entry)
            if holding:
                holdings.append(holding)

        return holdings

    def _parse_holding(self, entry: ET.Element) -> Optional[Holding]:
        """Parse a single holding entry from the XML."""
        def get_text(tag: str, default: str = "") -> str:
            # Try with namespace
            elem = entry.find(f"ns1:{tag}", self.NS)
            if elem is None:
                elem = entry.find(f"{{http://www.sec.gov/edgar/document/thirteenf/informationtable}}{tag}")
            if elem is None:
                elem = entry.find(tag)
            return elem.text.strip() if elem is not None and elem.text else default

        def get_int(tag: str, default: int = 0) -> int:
            text = get_text(tag)
            if text:
                # Remove commas and convert
                return int(text.replace(",", ""))
            return default

        # Get shrsOrPrnAmt sub-elements
        shrs_elem = entry.find("ns1:shrsOrPrnAmt", self.NS)
        if shrs_elem is None:
            shrs_elem = entry.find("{http://www.sec.gov/edgar/document/thirteenf/informationtable}shrsOrPrnAmt")
        if shrs_elem is None:
            shrs_elem = entry.find("shrsOrPrnAmt")

        shares = 0
        share_type = "SH"
        if shrs_elem is not None:
            amt_elem = shrs_elem.find("ns1:sshPrnamt", self.NS)
            if amt_elem is None:
                amt_elem = shrs_elem.find("{http://www.sec.gov/edgar/document/thirteenf/informationtable}sshPrnamt")
            if amt_elem is None:
                amt_elem = shrs_elem.find("sshPrnamt")
            if amt_elem is not None and amt_elem.text:
                shares = int(amt_elem.text.replace(",", ""))

            type_elem = shrs_elem.find("ns1:sshPrnamtType", self.NS)
            if type_elem is None:
                type_elem = shrs_elem.find("{http://www.sec.gov/edgar/document/thirteenf/informationtable}sshPrnamtType")
            if type_elem is None:
                type_elem = shrs_elem.find("sshPrnamtType")
            if type_elem is not None and type_elem.text:
                share_type = type_elem.text.strip()

        # Get voting authority sub-elements
        voting_elem = entry.find("ns1:votingAuthority", self.NS)
        if voting_elem is None:
            voting_elem = entry.find("{http://www.sec.gov/edgar/document/thirteenf/informationtable}votingAuthority")
        if voting_elem is None:
            voting_elem = entry.find("votingAuthority")

        voting_sole = voting_shared = voting_none = 0
        if voting_elem is not None:
            for vtype, attr in [("Sole", "voting_sole"), ("Shared", "voting_shared"), ("None", "voting_none")]:
                v_elem = voting_elem.find(f"ns1:{vtype}", self.NS)
                if v_elem is None:
                    v_elem = voting_elem.find(f"{{http://www.sec.gov/edgar/document/thirteenf/informationtable}}{vtype}")
                if v_elem is None:
                    v_elem = voting_elem.find(vtype)
                if v_elem is not None and v_elem.text:
                    if attr == "voting_sole":
                        voting_sole = int(v_elem.text.replace(",", ""))
                    elif attr == "voting_shared":
                        voting_shared = int(v_elem.text.replace(",", ""))
                    else:
                        voting_none = int(v_elem.text.replace(",", ""))

        return Holding(
            issuer=get_text("nameOfIssuer"),
            title=get_text("titleOfClass"),
            cusip=get_text("cusip"),
            value=get_int("value"),
            shares=shares,
            share_type=share_type,
            put_call=get_text("putCall") or None,
            investment_discretion=get_text("investmentDiscretion", "SOLE"),
            voting_sole=voting_sole,
            voting_shared=voting_shared,
            voting_none=voting_none,
        )

    def get_latest_filing(self) -> Filing:
        """Get the most recent 13F filing."""
        history = self.get_filing_history(limit=1)
        if not history:
            raise ValueError("No 13F filings found")
        return self.get_filing(history[0]["accession_number"])

    def get_last_two_filings(self) -> tuple[Filing, Filing]:
        """Get the two most recent 13F filings for comparison."""
        history = self.get_filing_history(limit=2)
        if len(history) < 2:
            raise ValueError("Need at least 2 filings for comparison")

        current = self.get_filing(history[0]["accession_number"])
        previous = self.get_filing(history[1]["accession_number"])

        return current, previous
