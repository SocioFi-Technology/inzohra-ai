# Inzohra-ai — top-level task runner
# Usage: make <target>

.PHONY: help dev dev-down seed-kb seed-packs ingest-codes ingest-fixture \
        review arch-review mep-review measure drafter compare letter \
        typecheck lint test

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Infrastructure ────────────────────────────────────────────────────────────

dev: ## Start local Docker stack (Postgres + Redis + MinIO)
	docker compose up -d postgres redis minio

dev-down: ## Stop and remove local Docker stack
	docker compose down

# ── Knowledge base ────────────────────────────────────────────────────────────

seed-kb: ## Seed code KB from hand-written SeedSections
	uv run scripts/kb/seed_kb.py

seed-packs: ## Seed jurisdictional amendment packs
	uv run scripts/kb/seed_packs.py

ingest-codes: ## Parse real Building Code PDFs → code_sections (uses Building Codes/ folder)
	uv run scripts/kb/ingest_code_pdfs.py --codes-dir "Building Codes"

# ── Plan ingestion ────────────────────────────────────────────────────────────

ingest-fixture: ## Ingest the 2008 Dennis Ln fixture plan set
	uv run scripts/ingest/ingest_all_fixture.py

# ── Review pipeline ───────────────────────────────────────────────────────────

review: ## Run full review pipeline on the fixture project
	uv run scripts/review/run_review.py

arch-review: ## Run arch + accessibility review only
	uv run scripts/review/run_arch_access_review.py

mep-review: ## Run MEP + structural review only
	uv run scripts/review/run_mep_structural_review.py

measure: ## Run measurement pipeline
	uv run scripts/review/run_measurement.py

drafter: ## Run comment drafter (produces letter JSON)
	uv run scripts/review/run_drafter.py

# ── Output ────────────────────────────────────────────────────────────────────

letter: ## Render the comment letter PDF/DOCX (requires drafter to have run first)
	pnpm --filter @inzohra/rendering render

compare: ## Compare AI output vs BV expected letter
	uv run scripts/review/run_comparison.py

# ── Quality ───────────────────────────────────────────────────────────────────

typecheck: ## TypeScript strict check (web + rendering)
	cd apps/web && npx tsc --noEmit
	cd apps/rendering && npx tsc --noEmit

lint: ## Python ruff + mypy strict
	uv run ruff check services/ scripts/ packages/shared-py/
	uv run mypy services/ --strict

test: ## Run all tests
	uv run pytest services/
