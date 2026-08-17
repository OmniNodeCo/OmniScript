.PHONY: install test check examples format build executable

install:
	python3 -m pip install -e .

test:
	python3 -m unittest discover -s tests -v

check:
	omni check examples/*.omni examples/lib/*.omni
	omni fmt --check examples/*.omni examples/lib/*.omni examples/tests/*.omni

examples:
	omni run examples/tour.omni
	omni test examples/tests

format:
	omni fmt examples/*.omni examples/lib/*.omni examples/tests/*.omni

build:
	python3 -m build

executable:
	./scripts/build_all_local.sh
