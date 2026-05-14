.PHONY: install install-global update lint run help

install:
	uv sync
	cp -n .env.example .env || true
	@echo ""
	@echo "Done. Run without activating venv:"
	@echo "  uv run pam --help"
	@echo ""
	@echo "Or activate once and use pam directly:"
	@echo "  source .venv/bin/activate"

install-global:
	uv tool install .
	cp -n .env.example .env || true
	@echo ""
	@echo "Done. pam is available globally (no venv needed):"
	@echo "  pam --help"

update:
	uv sync --upgrade
	uv tool install . --reinstall

lint:
	uv run ruff check src/
	uv run ruff format --check src/

help:
	uv run pam --help
