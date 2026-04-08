.PHONY: help docs docs_en docs_zh pdocs rst_auto test unittest benchmark benchmark_smoke benchmark_standard benchmark_phase9 benchmark_phase9_smoke benchmark_phase9_standard benchmark_phase9_pressure benchmark_compare build test_cli package clean

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
	@echo ""
	@echo "Testing:"
	@echo "  make test         - Run all tests (alias for unittest)"
	@echo "  make unittest     - Run unit tests with pytest and coverage"
	@echo "                      Options: RANGE_DIR=<dir> COV_TYPES='xml term-missing'"
	@echo "                               MIN_COVERAGE=<percent> WORKERS=<n>"
	@echo "  make benchmark    - Run pytest benchmark suite into build/benchmark/"
	@echo "                      Options: BENCHMARK_SCALE=<smoke|standard|stress>"
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
	@echo "  make benchmark_compare"
	@echo "                    - Compare two pytest-benchmark JSON files"
	@echo "                      Options: BENCHMARK_BASELINE=<path> BENCHMARK_CANDIDATE=<path>"
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

package:
	$(PYTHON) -m build --sdist --wheel --outdir ${DIST_DIR}

build:
	@test -f ${CLI_ENTRY} || (echo "Missing CLI entry file: ${CLI_ENTRY}" && exit 1)
	pyinstaller -F -n ${PROJECT_NAME} -c ${RESOURCE_ARGS} ${CLI_ENTRY}

test_cli:
	@test -f ${CLI_BIN} || (echo "Missing CLI executable: ${CLI_BIN}. Run 'make build' first." && exit 1)
	$(PYTHON) -m tools.test_cli ${CLI_BIN}

clean:
	rm -rf ${DIST_DIR} ${BUILD_DIR} *.egg-info
	rm -f ${PROJECT_NAME}.spec junit.xml

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
