import pathlib

import datamodel_code_generator as dcg
from hatchling.builders.hooks.plugin import interface


class GenerateDatamodelHook(interface.BuildHookInterface):
    PLUGIN_NAME = "generate_datamodel"
    CRLF = b"\r\n"
    LF = b"\n"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.__schema_dir = pathlib.Path.cwd() / "datam8-model" / "schema"
        self.__output_dir = pathlib.Path.cwd() / "src" / "datam8_model"
        self.__template_dir = pathlib.Path.cwd() / "template"

    def initialize(self, version, build_data):
        dcg.generate(
            input_=self.__schema_dir,
            input_file_type=dcg.InputFileType.JsonSchema,
            output=self.__output_dir,
            output_model_type=dcg.DataModelType.PydanticV2BaseModel,
            output_datetime_class=dcg.DatetimeClassType.Datetime,
            target_python_version=dcg.PythonVersion.PY_312,
            custom_template_dir=self.__template_dir,
            formatters=[dcg.Formatter.RUFF_CHECK, dcg.Formatter.RUFF_FORMAT],
            additional_imports=["pathlib.Path"],
            disable_timestamp=True,
            set_default_enum_member=True,
            capitalise_enum_members=True,
            collapse_root_models=True,
            allow_extra_fields=False,
            use_annotated=True,
            field_constraints=True,
            use_generic_container_types=True,
            use_schema_description=True,
            use_field_description=True,
            use_double_quotes=True,
            use_title_as_name=True,
            use_union_operator=True,
            custom_file_header_path=pathlib.Path("./license_file_header.txt"),
        )

        # self.prepend_license_to_files()

        self.convert_crlf_to_lf()

    def clean(self, versions):
        self.__output_dir.rmdir()

    def convert_crlf_to_lf(self):
        for file in self.__output_dir.glob("**/*.py"):
            with open(file, "rb") as f:
                content = f.read()

            content = content.replace(self.CRLF, self.LF)

            with open(file, "wb") as f:
                f.write(content)
