"""Bundle the pinned ODCS schema and its license with standalone DataM8 builds."""

from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("datam8", includes=["plugins/builtins/resources/*"])
