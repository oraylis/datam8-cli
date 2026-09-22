alias r := run
alias c := check-format
alias s := sync
alias b := build
alias rt := run-tests
alias ct := check-format-tests

# recipe run when executing just without arguments (run)
default: run

# sync the python venv with the definitions in uv.lock for development
sync *args:
  uv sync --all-extras {{ args }}

# shorthand to run datam8 via uv
run *args:
  uv run datam8 {{ args }}

# generates the common data model from datam8-model and builds the whl file
build *args:
  uv build {{ args }}

# run basic checks and formats source files
[group('checks')]
check-format: (_check-format-dir "src")

# run basic checks and formats for test files
[group('checks')]
check-format-tests: (_check-format-dir "tests")

_check-format-dir dir: sync
  uvx ty check {{ dir }}
  uvx ruff check {{ dir }} --fix
  uvx ruff format {{ dir }}

# run pytest test configuration in /tests
[group('tests')]
run-tests: sync
  uv run pytest tests

# initializes the datam8-model submodule
[group('datam8-model')]
setup-submodule:
  git submodule init datam8-model

# pull the newest version of the datma8 repo into the submodule
[group('datam8-model')]
upgrade-submodule: setup-submodule
  git submodule update --remote datam8-model
