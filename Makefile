SHELL := /bin/bash
.DEFAULT_GOAL := help

# Docker if the daemon is reachable, otherwise rootless Podman (same CLI for what we use).
CONTAINER ?= $(shell docker info >/dev/null 2>&1 && echo docker || echo podman)
MONGO_NAME ?= overclouded-mongo
MONGO_IMAGE ?= docker.io/library/mongo:8.0
BACKEND := backend
WEB := apps/web
INFRA := infra
UV := uv --directory $(BACKEND)
CDK := npx --yes aws-cdk@2.1142.0

.PHONY: help
help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- setup
.PHONY: setup
setup: .env ## Install all dependencies (backend, web, infra) and create .env
	$(UV) sync --frozen
	cd $(WEB) && npm ci
	cd $(INFRA) && uv sync --frozen

.env:
	@cp .env.example .env
	@secret=$$(python3 -c "import secrets;print(secrets.token_urlsafe(48))"); \
	  sed -i.bak "s|^DEV_JWT_SECRET=.*|DEV_JWT_SECRET=$$secret|" .env && rm -f .env.bak
	@echo "Created .env with a fresh local DEV_JWT_SECRET"

# ---------------------------------------------------------------- local run
.PHONY: mongo-up mongo-down
mongo-up: ## Start local MongoDB (single-node replica set)
	@if ! $(CONTAINER) ps --format '{{.Names}}' | grep -qx $(MONGO_NAME); then \
	  $(CONTAINER) run -d --rm --name $(MONGO_NAME) -p 127.0.0.1:27017:27017 \
	    $(MONGO_IMAGE) --replSet rs0 --bind_ip_all >/dev/null; \
	fi
	@for i in $$(seq 1 40); do \
	  $(CONTAINER) exec $(MONGO_NAME) mongosh --quiet --eval \
	    "try { rs.status().ok } catch (e) { rs.initiate({_id:'rs0',members:[{_id:0,host:'localhost:27017'}]}).ok }" \
	    >/dev/null 2>&1 && break; sleep 1; done
	@sleep 2; echo "MongoDB ready on localhost:27017 (rs0)"

mongo-down: ## Stop local MongoDB
	-$(CONTAINER) stop $(MONGO_NAME)

.PHONY: dev
dev: .env mongo-up seed ## Run MongoDB + API + web locally in Sample Data Mode (no AWS needed)
	@set -a; source .env; set +a; \
	  ( $(UV) run uvicorn overclouded.api.app:app --reload --port 8000 & echo $$! > .api.pid ); \
	  trap 'kill $$(cat .api.pid) 2>/dev/null; rm -f .api.pid' EXIT; \
	  cd $(WEB) && VITE_API_URL=http://localhost:8000 VITE_AUTH_MODE=dev npm run dev

.PHONY: api
api: .env mongo-up ## Run only the API with reload
	@set -a; source .env; set +a; $(UV) run uvicorn overclouded.api.app:app --reload --port 8000

.PHONY: seed reset
seed: .env mongo-up ## Run index migrations and seed the Sample Data Mode org
	@set -a; source .env; set +a; $(UV) run python -m overclouded.repos.migrate && \
	  $(UV) run python ../scripts/seed.py

reset: .env mongo-up ## Drop and re-seed the sample org
	@set -a; source .env; set +a; $(UV) run python ../scripts/reset.py

# ---------------------------------------------------------------- quality
.PHONY: lint format typecheck
lint: ## Ruff lint + format check (backend, infra, scripts), ESLint (web)
	$(UV) run ruff check src tests ../scripts ../infra
	$(UV) run ruff format --check src tests ../scripts ../infra
	cd $(WEB) && npm run lint

format: ## Auto-format
	$(UV) run ruff check --fix src tests ../scripts ../infra
	$(UV) run ruff format src tests ../scripts ../infra

typecheck: ## mypy --strict (backend) + tsc (web)
	$(UV) run mypy src
	cd $(WEB) && npm run typecheck

.PHONY: test test-unit test-integration coverage
test: test-unit test-integration ## All backend tests

test-unit: ## Unit, property and contract tests (no MongoDB needed)
	$(UV) run pytest tests/unit tests/property tests/contract -q

test-integration: mongo-up ## Integration tests against a real MongoDB
	MONGODB_URI='mongodb://localhost:27017/?replicaSet=rs0&directConnection=true' \
	  $(UV) run pytest tests/integration -q -m integration

coverage: ## Domain coverage (must be >= 90%)
	$(UV) run pytest tests/unit tests/property -q --cov=overclouded.domain --cov-report=term-missing --cov-fail-under=90

.PHONY: openapi client client-check
openapi: ## Export the OpenAPI schema
	$(UV) run python ../scripts/export_openapi.py ../$(WEB)/src/api/openapi.json

client: openapi ## Regenerate the TypeScript API client from the schema
	cd $(WEB) && npm run gen:api

client-check: ## Fail if the committed client is stale
	$(UV) run python ../scripts/export_openapi.py /tmp/overclouded-openapi.json
	diff -q /tmp/overclouded-openapi.json $(WEB)/src/api/openapi.json
	cd $(WEB) && npm run gen:api && git diff --exit-code -- src/api/schema.d.ts

.PHONY: web-build e2e
web-build: ## Production build of the web app
	cd $(WEB) && npm run build

e2e: ## Playwright E2E (needs `make dev` running in another terminal)
	cd $(WEB) && npx playwright test

.PHONY: verify-aws check-links
verify-aws: ## Re-verify AWS operations/fields against the installed botocore models
	$(UV) run python ../scripts/verify_aws_models.py

check-links: ## Check every AWS/Atlas documentation link we cite
	$(UV) run python ../scripts/check_links.py --docs

.PHONY: policy-lint secret-scan audit
policy-lint: ## Fail if the customer role grants any write action or Action "*"
	$(UV) run python ../scripts/policy_lint.py ../infra/customer-role/overclouded-readonly-role.yaml

secret-scan: ## Scan the working tree for secrets (gitleaks via container)
	$(CONTAINER) run --rm -v $(CURDIR):/repo:Z docker.io/zricethezav/gitleaks:v8.21.2 detect --source /repo --no-git -v

audit: ## Dependency audits
	$(UV) run pip-audit
	cd $(WEB) && npm audit --audit-level=high

# ---------------------------------------------------------------- AWS
.PHONY: synth deploy teardown lambda-bundle
lambda-bundle: ## Build the Lambda zip bundle (linux x86_64 wheels)
	bash scripts/build_lambda.sh

synth: lambda-bundle ## cdk synth (no AWS calls beyond context lookups)
	cd $(INFRA) && $(CDK) synth --quiet --app "uv run python app.py"

deploy: lambda-bundle web-build ## Deploy all stacks (uses AWS_PROFILE; never access keys)
	@test -n "$$AWS_PROFILE" || (echo "Set AWS_PROFILE to your SSO/deployer profile"; exit 1)
	cd $(INFRA) && $(CDK) deploy --all --require-approval broadening --app "uv run python app.py" \
	  --outputs-file ../.cdk-outputs.json
	@echo "Outputs written to .cdk-outputs.json. Next: make seed-cloud"

.PHONY: seed-cloud
seed-cloud: ## Seed the deployed sample org + Cognito demo users
	@test -n "$$AWS_PROFILE" || (echo "Set AWS_PROFILE"; exit 1)
	$(UV) run python ../scripts/seed_cloud.py ../.cdk-outputs.json

teardown: ## Destroy every stack, including buckets (asks for confirmation)
	@read -p "Destroy ALL Overclouded stacks and data in $$AWS_PROFILE? Type 'destroy': " ans; \
	  test "$$ans" = destroy || (echo aborted; exit 1)
	bash scripts/teardown.sh
