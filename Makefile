.PHONY: help install dev test lint format type-check clean run

# Default target
help:
	@echo "Available targets:"
	@echo "  install      - Install core dependencies"
	@echo "  dev          - Install development dependencies"
	@echo "  test         - Run test suite"
	@echo "  lint         - Run ruff linter"
	@echo "  format       - Format code with ruff"
	@echo "  type-check   - Run type checker (pyright)"
	@echo "  security     - Run security checks (bandit, pip-audit)"
	@echo "  clean        - Remove build artifacts"
	@echo "  run          - Run example (implement as needed)"

# Installation
install:
	uv pip install -e .

dev:
	uv pip install -e ".[dev]"

# Testing
test:
	pytest

test-fast:
	pytest -m "not slow"

test-cov:
	pytest --cov --cov-report=html --cov-report=term

# Linting and formatting
lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/
	ruff check src/ tests/ --fix

# Type checking
type-check:
	pyright src/

# Security
security:
	bandit -r src/
	pip-audit

# Cleaning
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf build/ dist/ *.egg-info htmlcov/

# Running (customize as needed)
run:
	@echo "Implement your run target here"
	# python -m src.main
