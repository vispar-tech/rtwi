.PHONY: help install fix lint types test check clean pre-commit binary package installer

POETRY ?= poetry

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies (with dev group)
	$(POETRY) install

fix: ## Format and auto-fix code with ruff (mutates files)
	$(POETRY) run ruff format .
	$(POETRY) run ruff check . --fix

lint: ## Lint check only with ruff (no changes)
	$(POETRY) run ruff check .
	$(POETRY) run ruff format --check .

types: ## Type-check with mypy
	$(POETRY) run mypy rtwi/

test: ## Run tests
	$(POETRY) run pytest

check: lint types test ## Verify: lint + types + tests (no changes)

clean: ## Remove build artifacts
	rm -rf dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

pre-commit: ## Run pre-commit hooks on all files
	$(POETRY) run pre-commit run -a

installer: ## Install the standalone rtwi binary
	./install.sh

binary: ## Build a standalone onedir rtwi into dist/rtwi/ (PyInstaller rtwi.spec)
	$(POETRY) run pyinstaller --noconfirm --clean rtwi.spec

package: binary ## Package dist/rtwi/ as dist/rtwi-<os>-<arch>.tar.gz (launcher + _internal/ at root)
	@os=`uname -s | tr '[:upper:]' '[:lower:]'`; \
	arch=`uname -m`; \
	case "$$arch" in x86_64|amd64) arch=x86_64;; arm64|aarch64) arch=aarch64;; esac; \
	echo "packaging dist/rtwi -> dist/rtwi-$$os-$$arch.tar.gz"; \
	cd dist/rtwi && tar -czf ../rtwi-$$os-$$arch.tar.gz .