# Gavin Baker Portfolio Tracker

Track Gavin Baker's Atreides Management portfolio movements from SEC 13F filings and post updates to X.com (Twitter).

## About

[Gavin Baker](https://en.wikipedia.org/wiki/Gavin_Baker_(investor)) is the founder and CIO of Atreides Management, LP. He previously managed Fidelity's OTC Portfolio (2009-2017). This tool monitors his quarterly 13F filings and posts portfolio changes to X.com.

**SEC CIK:** 0001777813

## Features

- Fetches 13F filings directly from SEC EDGAR (no paid APIs required)
- Compares current quarter to previous quarter
- Detects new positions, closed positions, increases, and decreases
- Posts updates as a Twitter thread or single tweet
- Dry-run mode for testing without posting

## Installation

```bash
# Clone the repository
git clone https://github.com/rajsinghtech/gavin-baker-tracker.git
cd gavin-baker-tracker

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

### SEC EDGAR (Required)

The SEC requires a User-Agent header with your contact info:

```
SEC_USER_AGENT="YourName your@email.com"
```

### X.com API (Required for posting)

1. Go to [X Developer Portal](https://developer.x.com/en/portal/dashboard)
2. Create a project and app
3. Generate OAuth 1.0a credentials (API Key + Secret, Access Token + Secret)
4. Add to your `.env`:

```
TWITTER_API_KEY="your_api_key"
TWITTER_API_SECRET="your_api_secret"
TWITTER_ACCESS_TOKEN="your_access_token"
TWITTER_ACCESS_SECRET="your_access_secret"
```

**Note:** X API Basic tier ($200/month) is recommended for production. Free tier limits you to 17 tweets/day.

## Usage

### View Portfolio Summary (No Twitter)

```bash
python -m src.main --summary-only
```

### Dry Run (Preview Tweets)

```bash
python -m src.main --dry-run
```

### Post to X.com

```bash
# Post as a thread
python -m src.main

# Post as a single tweet
python -m src.main --single-tweet
```

### Options

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview tweets without posting |
| `--single-tweet` | Post one tweet instead of a thread |
| `--summary-only` | Print summary without posting |
| `--user-agent` | Override SEC User-Agent |
| `--threshold` | Position change threshold (default: 0.05 = 5%) |

## Example Output

```
🚨 Gavin Baker's Atreides Management 13F Update

📊 Q4 Portfolio: $5.13B
📈 Change: +12.3%

🔄 47 position changes
Thread 🧵👇
```

## 13F Filing Schedule

| Quarter End | Filing Deadline |
|-------------|-----------------|
| March 31 | May 15 |
| June 30 | August 14 |
| September 30 | November 14 |
| December 31 | February 14 |

**Note:** 13F data shows positions as of quarter-end and can be up to 45 days old when filed. Current holdings may differ.

## Data Sources

- **SEC EDGAR:** Free, official source for 13F filings
- **Alternative:** [WhaleWisdom](https://whalewisdom.com/filer/atreides-management-lp), [HedgeFollow](https://hedgefollow.com/funds/Atreides+Management+Lp)

## Project Structure

```
gavin-baker-tracker/
├── src/
│   ├── fetcher/
│   │   ├── __init__.py
│   │   └── edgar.py       # SEC EDGAR API client
│   ├── analyzer/
│   │   ├── __init__.py
│   │   └── compare.py     # Portfolio comparison logic
│   ├── poster/
│   │   ├── __init__.py
│   │   └── twitter.py     # X.com posting
│   ├── __init__.py
│   └── main.py            # CLI entry point
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Limitations

- 13F filings only show long positions (no shorts)
- Options positions show held puts/calls only (not written)
- Data excludes: cash, private investments, foreign-only securities
- Filing delay: Up to 45 days after quarter end

## License

MIT
