.PHONY: install run dry-run summary post post-single post-force clean help

# Default target
help:
	@echo "Gavin Baker Portfolio Tracker"
	@echo ""
	@echo "Usage:"
	@echo "  make install      - Create venv and install dependencies"
	@echo "  make run          - Run with dry-run (preview tweets)"
	@echo "  make dry-run      - Same as 'make run'"
	@echo "  make summary      - Show portfolio summary only"
	@echo "  make post         - Post thread to X.com (skips if already posted)"
	@echo "  make post-single  - Post single tweet to X.com"
	@echo "  make post-force   - Force post even if already posted"
	@echo "  make clean        - Remove venv and cache files"

# Install dependencies
install:
	python3 -m venv venv
	. venv/bin/activate && pip install -r requirements.txt
	@echo ""
	@echo "Done! Run 'source venv/bin/activate' to activate the environment"

# Dry run (preview tweets)
run: dry-run

dry-run:
	. venv/bin/activate && set -a && source .env && set +a && python -m src.main --dry-run

# Summary only (no tweets)
summary:
	. venv/bin/activate && set -a && source .env && set +a && python -m src.main --summary-only

# Post thread to X.com (skips duplicates)
post:
	. venv/bin/activate && set -a && source .env && set +a && python -m src.main

# Post single tweet to X.com
post-single:
	. venv/bin/activate && set -a && source .env && set +a && python -m src.main --single-tweet

# Force post even if already posted
post-force:
	. venv/bin/activate && set -a && source .env && set +a && python -m src.main --force

# Clean up
clean:
	rm -rf venv __pycache__ src/__pycache__ src/*/__pycache__ .pytest_cache
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
