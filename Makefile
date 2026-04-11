.PHONY: help docs docs_en docs_zh pdocs rst_auto test unittest benchmark benchmark_smoke benchmark_standard benchmark_phase9 benchmark_phase9_smoke benchmark_phase9_standard benchmark_phase9_pressure benchmark_phase12 benchmark_phase12_raw benchmark_phase12_summary benchmark_phase12_smoke benchmark_phase12_standard benchmark_phase12_nightly benchmark_phase12_pressure benchmark_compare benchmark_phase12_compare build test_cli package clean webui_install webui_test webui_coverage webui_e2e webui_build webui_sync webui_package webui_check webui_clean

PYTHON := $(shell [ -x ./venv/bin/python ] && printf '%s' ./venv/bin/python || which python)
SPHINXBUILD ?= $(shell which sphinx-build)
SPHINXMULTIVERSION ?= $(shell which sphinx-multiversion)

PROJECT_NAME := hubvault
PROJ_DIR     := .
DOC_DIR      := ${PROJ_DIR}/docs
BUILD_DIR    := ${PROJ_DIR}/build
DIST_DIR     := ${PROJ_DIR}/dist
TEST_DIR     := ${PROJ_DIR}/test
SRC_DIR      := ${PROJ_DIR}/${PROJECT_NAME}
TOOLS_DIR    := ${PROJ_DIR}/tools
CLI_ENTRY    := ${PROJ_DIR}/hubvault_cli.py
CLI_BIN      := ${DIST_DIR}/${PROJECT_NAME}$(if ${IS_WIN},.exe,)
WEBUI_DIR    := ${PROJ_DIR}/webui
WEBUI_DIST_DIR := ${WEBUI_DIR}/dist
WEBUI_STATIC_DIR := ${SRC_DIR}/server/static/webui
WEBUI_REPORT_DIR := ${WEBUI_DIR}/playwright-report
WEBUI_RESULTS_DIR := ${WEBUI_DIR}/test-results
WEBUI_COVERAGE_DIR := ${WEBUI_DIR}/coverage
WEBUI_VITE_CACHE_DIR := ${WEBUI_DIR}/node_modules/.vite
WEBUI_INSTALL_STAMP := ${WEBUI_DIR}/node_modules/.hubvault-install.stamp
WEBUI_BUILD_STAMP := ${BUILD_DIR}/webui/.hubvault-build.stamp
WEBUI_LEGACY_BUILD_STAMP := ${WEBUI_DIST_DIR}/.hubvault-build.stamp
NPM ?= $(shell which npm)
WEBUI_INSTALL_ACTION := $(if $(wildcard ${WEBUI_DIR}/package-lock.json),ci,install)
WEBUI_INSTALL_DEPS := ${WEBUI_DIR}/package.json
WEBUI_BUILD_DEPS := $(shell find ${WEBUI_DIR}/src -type f 2>/dev/null) \
	$(shell find ${WEBUI_DIR}/tests -type f 2>/dev/null) \
	${WEBUI_DIR}/index.html \
	${WEBUI_DIR}/package.json \
	${WEBUI_DIR}/vite.config.ts \
	${WEBUI_DIR}/vitest.config.ts \
	${WEBUI_DIR}/playwright.config.ts \
	${WEBUI_DIR}/tsconfig.json \
	${WEBUI_DIR}/env.d.ts
ifneq ($(wildcard ${WEBUI_DIR}/package-lock.json),)
WEBUI_INSTALL_DEPS += ${WEBUI_DIR}/package-lock.json
WEBUI_BUILD_DEPS += ${WEBUI_DIR}/package-lock.json
endif

RANGE_DIR           ?= .
RANGE_TEST_DIR      := ${TEST_DIR}/${RANGE_DIR}
RANGE_SRC_DIR       := ${SRC_DIR}/${RANGE_DIR}
PYTHON_CODE_DIR     := ${SRC_DIR}
RST_DOC_DIR         := ${DOC_DIR}/source/api_doc
PYTHON_CODE_FILES   := $(shell find ${PYTHON_CODE_DIR} -name "*.py" ! -name "__*.py" 2>/dev/null)
RST_DOC_FILES       := $(patsubst ${PYTHON_CODE_DIR}/%.py,${RST_DOC_DIR}/%.rst,${PYTHON_CODE_FILES})
PYTHON_NONM_FILES   := $(shell find ${PYTHON_CODE_DIR} -name "__init__.py" 2>/dev/null)
RST_NONM_FILES      := $(foreach file,${PYTHON_NONM_FILES},$(patsubst %/__init__.py,%/index.rst,$(patsubst ${PYTHON_CODE_DIR}/%,${RST_DOC_DIR}/%,$(patsubst ${PYTHON_CODE_DIR}/__init__.py,${RST_DOC_DIR}/index.rst,${file}))))

COV_TYPES     ?= xml term-missing
RESOURCE_ARGS := $(shell $(PYTHON) -m tools.resources 2>/dev/null)
BENCHMARK_DIR ?= ${BUILD_DIR}/benchmark
BENCHMARK_JSON ?= ${BENCHMARK_DIR}/pytest-benchmark.json
BENCHMARK_FILTER ?=
BENCHMARK_SCALE ?= standard
BENCHMARK_SCENARIO_SET ?= full
BENCHMARK_PHASE9_JSON ?= ${BENCHMARK_DIR}/phase9-summary.json
BENCHMARK_PHASE12_ROOT ?= ${BENCHMARK_DIR}/phase12
BENCHMARK_PHASE12_RAW_DIR ?= ${BENCHMARK_PHASE12_ROOT}/raw
BENCHMARK_PHASE12_SUMMARY_DIR ?= ${BENCHMARK_PHASE12_ROOT}/summary
BENCHMARK_PHASE12_COMPARE_DIR ?= ${BENCHMARK_PHASE12_ROOT}/compare
BENCHMARK_PHASE12_MANIFEST_DIR ?= ${BENCHMARK_PHASE12_ROOT}/manifests
BENCHMARK_PHASE12_RAW_JSON ?= ${BENCHMARK_PHASE12_RAW_DIR}/pytest-benchmark-${BENCHMARK_SCALE}.json
BENCHMARK_PHASE12_SUMMARY_JSON ?= ${BENCHMARK_PHASE12_SUMMARY_DIR}/phase12-${BENCHMARK_SCALE}-${BENCHMARK_SCENARIO_SET}.json
BENCHMARK_PHASE12_MANIFEST_JSON ?= ${BENCHMARK_PHASE12_MANIFEST_DIR}/phase12-${BENCHMARK_SCALE}-${BENCHMARK_SCENARIO_SET}-manifest.json
BENCHMARK_PHASE12_COMPARE_JSON ?= ${BENCHMARK_PHASE12_COMPARE_DIR}/phase12-compare.json
BENCHMARK_STORAGE ?= file://${BENCHMARK_PHASE12_RAW_DIR}/autosave
BENCHMARK_SAVE_NAME ?= phase12-${BENCHMARK_SCALE}-${BENCHMARK_SCENARIO_SET}
BENCHMARK_BASELINE ?=
BENCHMARK_CANDIDATE ?=

help:
	@echo "hubvault Build System"
	@echo "===================="
	@echo ""
	@echo "Building and Packaging:"
	@echo "  make package      - Build Python package (sdist and wheel)"
	@echo "  make build        - Build standalone executable with PyInstaller"
	@echo "  make clean        - Remove build and packaging artifacts"
	@echo "  make webui_install"
	@echo "                    - Install frontend dependencies with npm ci/install"
	@echo "  make webui_test   - Run frontend unit/component tests"
	@echo "  make webui_coverage"
	@echo "                    - Run frontend unit/component tests with detailed coverage output"
	@echo "  make webui_e2e    - Run frontend Playwright end-to-end checks"
	@echo "  make webui_build  - Build frontend assets into webui/dist/"
	@echo "  make webui_sync   - Sync webui/dist/ into hubvault/server/static/webui/"
	@echo "  make webui_package"
	@echo "                    - Build frontend assets and deploy them into the Python package path"
	@echo "  make webui_check  - Run frontend tests and end-to-end checks"
	@echo "  make webui_clean  - Remove frontend dist/ and transient test/report artifacts"
	@echo ""
	@echo "Testing:"
	@echo "  make test         - Run all tests (alias for unittest)"
	@echo "  make unittest     - Run unit tests with pytest and coverage"
	@echo "                      Options: RANGE_DIR=<dir> COV_TYPES='xml term-missing'"
	@echo "                               MIN_COVERAGE=<percent> WORKERS=<n>"
	@echo "  make benchmark    - Run pytest benchmark suite into build/benchmark/"
	@echo "                      Options: BENCHMARK_SCALE=<smoke|standard|nightly|stress|pressure>"
	@echo "                               BENCHMARK_FILTER='<pytest -k expr>' BENCHMARK_JSON=<path>"
	@echo "  make benchmark_smoke"
	@echo "                    - Run the pytest benchmark suite with BENCHMARK_SCALE=smoke"
	@echo "  make benchmark_standard"
	@echo "                    - Run the pytest benchmark suite with BENCHMARK_SCALE=standard"
	@echo "  make benchmark_phase9"
	@echo "                    - Run the curated Phase 9 benchmark runner and emit a JSON summary"
	@echo "                      Options: BENCHMARK_SCALE=<smoke|standard|stress|pressure>"
	@echo "                               BENCHMARK_SCENARIO_SET=<full|pressure> BENCHMARK_PHASE9_JSON=<path>"
	@echo "  make benchmark_phase9_smoke"
	@echo "                    - Run the curated Phase 9 runner with the smoke/full baseline suite"
	@echo "  make benchmark_phase9_standard"
	@echo "                    - Run the curated Phase 9 runner with the standard/full baseline suite"
	@echo "  make benchmark_phase9_pressure"
	@echo "                    - Run the GB-scale pressure subset focused on large-file IO and dedup space behavior"
	@echo "  make benchmark_phase12"
	@echo "                    - Run the default Phase 12 standard benchmark entry (raw pytest + curated summary + manifest)"
	@echo "  make benchmark_phase12_smoke"
	@echo "                    - Run the Phase 12 smoke tier and write raw/summary/manifests under build/benchmark/phase12/"
	@echo "  make benchmark_phase12_standard"
	@echo "                    - Run the Phase 12 standard tier with raw pytest output, curated summary, and manifest"
	@echo "  make benchmark_phase12_nightly"
	@echo "                    - Run the Phase 12 nightly tier with the expanded nightly dataset and artifact layout"
	@echo "  make benchmark_phase12_pressure"
	@echo "                    - Run the Phase 12 pressure curated summary for large-file IO, amplification, and host IO baselines"
	@echo "  make benchmark_compare"
	@echo "                    - Compare two pytest-benchmark JSON files"
	@echo "                      Options: BENCHMARK_BASELINE=<path> BENCHMARK_CANDIDATE=<path>"
	@echo "  make benchmark_phase12_compare"
	@echo "                    - Compare two Phase 12 raw or curated JSON files and persist a compare JSON report"
	@echo "  make test_cli     - Smoke test the built CLI executable"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs         - Build documentation"
	@echo "  make docs_en      - Build English documentation"
	@echo "  make docs_zh      - Build Chinese documentation"
	@echo "  make pdocs        - Build multi-version documentation"
	@echo "  make rst_auto     - Generate docs/source/api_doc/*.rst from Python source"
	@echo "                      Options: RANGE_DIR=<dir>"
	@echo ""
	@echo "Common Variables:"
	@echo "  RANGE_DIR=<dir>   - Target a specific source/test subtree (default: .)"
	@echo "  COV_TYPES=<types> - Coverage reports to generate (default: xml term-missing)"
	@echo "  MIN_COVERAGE=<n>  - Minimum required coverage percentage"
	@echo "  WORKERS=<n>       - Number of pytest-xdist workers"

package: webui_package
	rm -rf ${BUILD_DIR}/lib ${BUILD_DIR}/bdist.*
	$(PYTHON) -m build --sdist --wheel --outdir ${DIST_DIR}

webui_install: ${WEBUI_INSTALL_STAMP}

${WEBUI_INSTALL_STAMP}: ${WEBUI_INSTALL_DEPS}
	@test -f ${WEBUI_DIR}/package.json || (echo "Missing frontend package manifest: ${WEBUI_DIR}/package.json" && exit 1)
	@test -n "${NPM}" || (echo "npm not found. Install Node.js/npm first." && exit 1)
	cd ${WEBUI_DIR} && ${NPM} ${WEBUI_INSTALL_ACTION}
	@touch ${WEBUI_INSTALL_STAMP}

webui_test: webui_install
	cd ${WEBUI_DIR} && ${NPM} run test

webui_coverage: webui_install
	cd ${WEBUI_DIR} && ${NPM} run test:coverage

webui_e2e: webui_package
	cd ${WEBUI_DIR} && ${NPM} run test:e2e

webui_build: ${WEBUI_BUILD_STAMP}

${WEBUI_BUILD_STAMP}: ${WEBUI_INSTALL_STAMP} ${WEBUI_BUILD_DEPS}
	cd ${WEBUI_DIR} && ${NPM} run build
	@mkdir -p $(dir $@)
	@touch ${WEBUI_BUILD_STAMP}

webui_sync: webui_build
	rm -f ${WEBUI_LEGACY_BUILD_STAMP}
	$(PYTHON) -m tools.webui_sync

webui_package: webui_sync

webui_check: webui_test webui_e2e

webui_clean:
	rm -rf ${WEBUI_DIST_DIR} ${WEBUI_REPORT_DIR} ${WEBUI_RESULTS_DIR} ${WEBUI_COVERAGE_DIR} ${WEBUI_VITE_CACHE_DIR}
	rm -f ${WEBUI_BUILD_STAMP} ${WEBUI_LEGACY_BUILD_STAMP}

build: webui_package
	@test -f ${CLI_ENTRY} || (echo "Missing CLI entry file: ${CLI_ENTRY}" && exit 1)
	$(PYTHON) -m tools.generate_spec -o hubvault.spec
	pyinstaller hubvault.spec

test_cli:
	@test -f ${CLI_BIN} || (echo "Missing CLI executable: ${CLI_BIN}. Run 'make build' first." && exit 1)
	$(PYTHON) -m tools.test_cli ${CLI_BIN}

clean:
	rm -rf ${DIST_DIR} ${BUILD_DIR} *.egg-info
	rm -f ${PROJECT_NAME}.spec junit.xml
	@$(MAKE) webui_clean

test: unittest

unittest:
	UNITTEST=1 \
		$(PYTHON) -m pytest "${RANGE_TEST_DIR}" \
		-sv -m unittest \
		--junitxml=junit.xml -o junit_family=legacy \
		$(shell for type in ${COV_TYPES}; do echo "--cov-report=$$type"; done) \
		--cov="${RANGE_SRC_DIR}" \
		$(if ${MIN_COVERAGE},--cov-fail-under=${MIN_COVERAGE},) \
		$(if ${WORKERS},-n ${WORKERS},)

benchmark:
	@mkdir -p ${BENCHMARK_DIR}
	HUBVAULT_BENCHMARK_SCALE=${BENCHMARK_SCALE} \
		${PYTHON} -m pytest "${TEST_DIR}/benchmark" \
		-sv -m benchmark --benchmark-only \
		--benchmark-json="${BENCHMARK_JSON}" \
		$(if ${BENCHMARK_FILTER},-k "${BENCHMARK_FILTER}",)

benchmark_smoke:
	@$(MAKE) benchmark BENCHMARK_SCALE=smoke

benchmark_standard:
	@$(MAKE) benchmark BENCHMARK_SCALE=standard

benchmark_phase9:
	@mkdir -p ${BENCHMARK_DIR}
	HUBVAULT_BENCHMARK_SCALE=${BENCHMARK_SCALE} \
		${PYTHON} -m tools.benchmark.run_phase9 \
		--scale ${BENCHMARK_SCALE} \
		--scenario-set ${BENCHMARK_SCENARIO_SET} \
		--output "${BENCHMARK_PHASE9_JSON}"

benchmark_phase9_smoke:
	@$(MAKE) benchmark_phase9 BENCHMARK_SCALE=smoke BENCHMARK_SCENARIO_SET=full BENCHMARK_PHASE9_JSON="${BENCHMARK_DIR}/phase9-smoke-summary.json"

benchmark_phase9_standard:
	@$(MAKE) benchmark_phase9 BENCHMARK_SCALE=standard BENCHMARK_SCENARIO_SET=full BENCHMARK_PHASE9_JSON="${BENCHMARK_DIR}/phase9-standard-summary.json"

benchmark_phase9_pressure:
	@$(MAKE) benchmark_phase9 BENCHMARK_SCALE=pressure BENCHMARK_SCENARIO_SET=pressure BENCHMARK_PHASE9_JSON="${BENCHMARK_DIR}/phase9-pressure-summary.json"

benchmark_compare:
	@test -n "${BENCHMARK_BASELINE}" || (echo "Missing BENCHMARK_BASELINE=<path>" && exit 1)
	@test -n "${BENCHMARK_CANDIDATE}" || (echo "Missing BENCHMARK_CANDIDATE=<path>" && exit 1)
	${PYTHON} -m tools.benchmark.compare "${BENCHMARK_BASELINE}" "${BENCHMARK_CANDIDATE}"

benchmark_phase12: benchmark_phase12_standard

benchmark_phase12_raw:
	@mkdir -p ${BENCHMARK_PHASE12_RAW_DIR}
	HUBVAULT_BENCHMARK_SCALE=${BENCHMARK_SCALE} \
		${PYTHON} -m pytest "${TEST_DIR}/benchmark" \
		-sv -m benchmark --benchmark-only \
		--benchmark-save="${BENCHMARK_SAVE_NAME}" \
		--benchmark-save-data \
		--benchmark-storage="${BENCHMARK_STORAGE}" \
		--benchmark-json="${BENCHMARK_PHASE12_RAW_JSON}" \
		$(if ${BENCHMARK_FILTER},-k "${BENCHMARK_FILTER}",)

benchmark_phase12_summary:
	@mkdir -p ${BENCHMARK_PHASE12_SUMMARY_DIR} ${BENCHMARK_PHASE12_MANIFEST_DIR}
	HUBVAULT_BENCHMARK_SCALE=${BENCHMARK_SCALE} \
		${PYTHON} -m tools.benchmark.run_phase9 \
		--scale ${BENCHMARK_SCALE} \
		--scenario-set ${BENCHMARK_SCENARIO_SET} \
		--output "${BENCHMARK_PHASE12_SUMMARY_JSON}" \
		--manifest-output "${BENCHMARK_PHASE12_MANIFEST_JSON}"

benchmark_phase12_smoke:
	@$(MAKE) benchmark_phase12_raw \
		BENCHMARK_SCALE=smoke \
		BENCHMARK_SAVE_NAME=phase12-smoke-full
	@$(MAKE) benchmark_phase12_summary \
		BENCHMARK_SCALE=smoke \
		BENCHMARK_SCENARIO_SET=full

benchmark_phase12_standard:
	@$(MAKE) benchmark_phase12_raw \
		BENCHMARK_SCALE=standard \
		BENCHMARK_SAVE_NAME=phase12-standard-full
	@$(MAKE) benchmark_phase12_summary \
		BENCHMARK_SCALE=standard \
		BENCHMARK_SCENARIO_SET=full

benchmark_phase12_nightly:
	@$(MAKE) benchmark_phase12_raw \
		BENCHMARK_SCALE=nightly \
		BENCHMARK_SAVE_NAME=phase12-nightly-full
	@$(MAKE) benchmark_phase12_summary \
		BENCHMARK_SCALE=nightly \
		BENCHMARK_SCENARIO_SET=full

benchmark_phase12_pressure:
	@$(MAKE) benchmark_phase12_summary \
		BENCHMARK_SCALE=pressure \
		BENCHMARK_SCENARIO_SET=pressure

benchmark_phase12_compare:
	@test -n "${BENCHMARK_BASELINE}" || (echo "Missing BENCHMARK_BASELINE=<path>" && exit 1)
	@test -n "${BENCHMARK_CANDIDATE}" || (echo "Missing BENCHMARK_CANDIDATE=<path>" && exit 1)
	@mkdir -p ${BENCHMARK_PHASE12_COMPARE_DIR}
	${PYTHON} -m tools.benchmark.compare "${BENCHMARK_BASELINE}" "${BENCHMARK_CANDIDATE}" > "${BENCHMARK_PHASE12_COMPARE_JSON}"

docs:
	@if [ -f "${DOC_DIR}/Makefile" ]; then \
		$(MAKE) -C "${DOC_DIR}" build; \
	elif [ -f "${DOC_DIR}/source/conf.py" ]; then \
		"${SPHINXBUILD}" -M html "${DOC_DIR}/source" "${DOC_DIR}/build"; \
	else \
		echo "Documentation config not found under ${DOC_DIR}/"; \
		exit 1; \
	fi

docs_en:
	@if [ -f "${DOC_DIR}/Makefile" ]; then \
		READTHEDOCS_LANGUAGE=en $(MAKE) -C "${DOC_DIR}" build; \
	elif [ -f "${DOC_DIR}/source/conf.py" ]; then \
		READTHEDOCS_LANGUAGE=en "${SPHINXBUILD}" -M html "${DOC_DIR}/source" "${DOC_DIR}/build"; \
	else \
		echo "Documentation config not found under ${DOC_DIR}/"; \
		exit 1; \
	fi

docs_zh:
	@if [ -f "${DOC_DIR}/Makefile" ]; then \
		READTHEDOCS_LANGUAGE=zh-cn $(MAKE) -C "${DOC_DIR}" build; \
	elif [ -f "${DOC_DIR}/source/conf.py" ]; then \
		READTHEDOCS_LANGUAGE=zh-cn "${SPHINXBUILD}" -M html "${DOC_DIR}/source" "${DOC_DIR}/build"; \
	else \
		echo "Documentation config not found under ${DOC_DIR}/"; \
		exit 1; \
	fi

pdocs:
	@if [ -f "${DOC_DIR}/Makefile" ]; then \
		$(MAKE) -C "${DOC_DIR}" prod; \
	elif [ -f "${DOC_DIR}/source/conf.py" ] && [ -n "${SPHINXMULTIVERSION}" ]; then \
		"${SPHINXMULTIVERSION}" "${DOC_DIR}/source" "${DOC_DIR}/build/html"; \
	else \
		echo "Production documentation config not available under ${DOC_DIR}/"; \
		exit 1; \
	fi

rst_auto: ${RST_DOC_FILES} ${RST_NONM_FILES} auto_rst_top_index.py
	@mkdir -p ${DOC_DIR}/source
	$(PYTHON) auto_rst_top_index.py -i ${PYTHON_CODE_DIR} -o ${DOC_DIR}/source

${RST_DOC_DIR}/%.rst: ${PYTHON_CODE_DIR}/%.py auto_rst.py Makefile
	@mkdir -p $(dir $@)
	$(PYTHON) auto_rst.py -i $< -o $@

${RST_DOC_DIR}/%/index.rst: ${PYTHON_CODE_DIR}/%/__init__.py auto_rst.py Makefile
	@mkdir -p $(dir $@)
	$(PYTHON) auto_rst.py -i $< -o $@

${RST_DOC_DIR}/index.rst: ${PYTHON_CODE_DIR}/__init__.py auto_rst.py Makefile
	@mkdir -p $(dir $@)
	$(PYTHON) auto_rst.py -i $< -o $@
