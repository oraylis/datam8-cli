import glob
import jinja2
import sqlparse
import sys
import os
import json
import textwrap

from .Model import Model
from autopep8 import fix_code
import importlib
from ..Helper.Helper import Helper, Path, Cache, Hasher
import logging

logger = logging.getLogger(__name__)


class Jinja2Factory:
    """Factory class for Jinja2 templates."""

    errors: list = []
    logger: logging.Logger = None
    model: Model = None
    log_level: logging.log = None

    def __init__(self, model: Model, log_level: logging.log = logging.INFO):
        """Initialize the Jinja2Factory.

        Args:
            model (Model): The model object.
            log_level (logging.log, optional): The logging level. Defaults to logging.INFO.
        """
        self.log_level = log_level
        self.logger: logging.Logger = Helper.start_logger(
            self.__class__.__name__, log_level=self.log_level
        )
        self.model = model
        self.logger.debug("Successfully init Jinja2Factory")

    def get_errors(self) -> list:
        """Get errors.

        Returns:
            list: List of errors.
        """
        __ls_errors: list = self.errors + self.model.errors

        return __ls_errors

    def __error_handler(self, msg: str):
        """Handle errors.

        Args:
            msg (str): The error message.
        """
        self.errors.append(f"Error in JinjaFactory: {msg}")
        self.logger.error(msg)
        sys.exit(-1)

    def __delete_template(self, path_template: str):
        """Delete template.

        Args:
            path_template (str): The path to the template.
        """
        try:
            ls_target_files = [
                f
                for f in glob.iglob(path_template + "**/**", recursive=True)
                if os.path.isfile(f)
            ]
            for file in ls_target_files:
                self.logger.debug(f"Removing Template: {os.path.basename(file)}")
                os.remove(file)

        except Exception as e:
            self.__error_handler(str(e))

    def __get_file_name_from_line(self, identifier: str, line: str) -> str:
        """Get file name from line.

        Args:
            identifier (str): The identifier.
            line (str): The line.

        Returns:
            str: The file name.
        """
        file_name_start = line.rfind(identifier) + 1

        if "|" in line:
            file_name_end = line.rfind("|")
            file_name = line[file_name_start:file_name_end].strip()
        else:
            file_name = line[file_name_start : len(line)].strip()

        return file_name

    def __get_file_type_from_line(self, line: str) -> str:
        """Get file type from line.

        Args:
            line (str): The line.

        Returns:
            str: The file type.
        """
        file_type = ""
        if "|" in line:
            file_name_start = line.rfind("|") + 1
            file_type = line[file_name_start : len(line)].strip()

        return file_type

    def __format_file(self, file_type: str, file_path: str, file_name: str):
        """Format file.

        Args:
            file_type (str): The file type.
            file_path (str): The file path.
            file_name (str): The file name.
        """
        __file_type = file_type.lower()

        # Format json using json dumps
        if __file_type == "json":
            try:
                data = Helper.read_json(file_path)

                with open(file_path, encoding="utf-8", mode="w") as f:
                    formated_json = json.dumps(data, indent=4, ensure_ascii=False)
                    f.write(formated_json)

            except Exception as e:
                self.logger.warning(
                    f"Unable to format file {file_name} due to error {e} "
                )

        # Format python using
        elif __file_type == "py" or __file_type == "python":
            with open(file_path, "r") as f:
                data = f.read()

            try:
                autopep8_formatted_code = fix_code(data)
                with open(file_path, "w") as f:
                    f.write(autopep8_formatted_code)

            except Exception as e:
                self.logger.warning(
                    f"Unable to format file {file_name} due to error {e} "
                )

        elif __file_type == "sql":
            with open(file_path, "r") as f:
                data = f.read()

            try:
                sql_formatted_code = sqlparse.format(
                    data, reindent=True, keyword_case="upper"
                )
                with open(file_path, "w") as f:
                    f.write(sql_formatted_code)
            except Exception as e:
                self.logger.warning(
                    f"Unable to format file {file_name} due to error {e} "
                )

        else:
            self.logger.debug(
                f"Beautifier not executed due to unknow file_type: {file_type} for file: {file_name}"
            )

    def write_output(
        self, input_file_name: str, output: str, path_template_destination: str
    ):
        """Write output.

        Args:
            input_file_name (str): The input file name.
            output (str): The output.
            path_template_destination (str): The destination path for the template.
        """
        current_file = None

        try:
            for line in output.splitlines():
                strip_line = line.strip()
                if strip_line.startswith(">>>>>>>>>>"):
                    file_name = self.__get_file_name_from_line(
                        identifier=">", line=strip_line
                    )
                    file_path = os.path.join(path_template_destination, file_name)
                    directory_name = os.path.dirname(file_path)

                    if not os.path.exists(directory_name):
                        os.makedirs(directory_name)
                        self.logger.info(
                            f"Created template target directory: {path_template_destination}"
                        )

                    self.logger.debug(f"Opening file: {input_file_name}")
                    current_file = open(file_path, encoding="utf-8", mode="a")

                elif strip_line.startswith("<<<<<<<<<<"):
                    self.logger.debug(f"Closing file: {input_file_name}")
                    current_file.close()
                    current_file = None

                    # Beautifier Format File based on type
                    __file_type = self.__get_file_type_from_line(line=strip_line)
                    if __file_type:
                        __file_name = self.__get_file_name_from_line(
                            identifier="<", line=strip_line
                        )
                        __file_path = os.path.join(
                            path_template_destination, __file_name
                        )

                        self.logger.debug(
                            f"Detected file_type: {__file_type} for file: {__file_name} -> Beautfier exexcuting"
                        )
                        self.__format_file(
                            file_type=__file_type,
                            file_path=__file_path,
                            file_name=__file_name,
                        )

                else:
                    if current_file is not None:
                        current_file.write(line + "\n")
                    else:
                        if line.strip() != "":
                            self.logger.debug("WARNING: No Current File: " + line)

        except Exception as e:
            msg = """
                Error Generating Template!
                --------------------------
                Template:   {}
                Target:     {}
                Error:      {}
                Error-Type: {}

                An error occurred writing the output to the
                destination file
            """.format(
                input_file_name, current_file, e, type(e).__name__
            )

            self.__error_handler(msg)

    def generate_template(
        self,
        path_template_source: str,
        path_template_destination: str,
        path_modules: str = None,
        path_collections: str = None,
        path_solution: str = None,
    ):
        """Generate template.

        Args:
            path_template_source (str): The source path for the template.
            path_template_destination (str): The destination path for the template.
            path_modules (str, optional): The path to modules. Defaults to None.
            path_collections (str, optional): The path to collections. Defaults to None.
            path-solution (str, optional): The path to the dm8 solution file. Defaults to None.
        """
        try:
            _path_template_source = os.path.abspath(path_template_source)

            # Get Destination Folder and Source Template paths list
            _path_template_destination = os.path.abspath(path_template_destination)

            # Get List of jinja Template using globe for searching directories(Catch case for selecting a single jinja file)
            if os.path.isfile(_path_template_source):
                ls_glob = [_path_template_source]
            else:
                ls_glob = list(glob.glob(_path_template_source + "/**", recursive=True))

            # Get final template list and filesystem loader list (ignore templates from collection folder if collection parameter ist used)
            if path_collections is not None:
                _path_collections = os.path.abspath(path_collections)
                ls_templates_source = list(
                    filter(
                        lambda x: x.endswith("jinja2")
                        and not os.path.abspath(x).startswith(_path_collections),
                        ls_glob,
                    )
                )
                ls_filesystemloader = [_path_template_source, _path_collections]
            else:
                ls_templates_source = list(
                    filter(lambda x: x.endswith("jinja2"), ls_glob)
                )
                ls_filesystemloader = [_path_template_source]

            if path_solution is not None:
                ls_filesystemloader.append(Helper.get_parent_path(path_solution))

            # FileSystemLoader and Environment to enable template inheritance
            # templateLoader = jinja2.FileSystemLoader(searchpath=path_template_source)
            templateLoader = jinja2.FileSystemLoader(ls_filesystemloader)
            templateEnv = jinja2.Environment(loader=templateLoader)
            self.logger.info(
                f"Start generating output from directory: {_path_template_source}"
            )

            # Template Input Parameter
            cache = Cache()
            dict_modules: dict = {"cache": cache, "Hasher": Hasher}
            # Create enhanced model context with v2 unified entity support
            dict_model: dict = {
                "model": self.model,
                "unified_entities": self.model.get_unified_entity_list(),
                "unified_entities_by_layer": {
                    "raw": self.model.get_unified_entities_by_layer("raw"),
                    "staging": self.model.get_unified_entities_by_layer("staging"), 
                    "core": self.model.get_unified_entities_by_layer("core"),
                    "curated": self.model.get_unified_entities_by_layer("curated"),
                },
                # Provide derived raw entities from staging (v2 only now)
                "v2_derived_raw_entities": self.model.get_entity_list_by_layer("raw")
            }
            if path_modules is not None:
                path_modules = os.path.abspath(path_modules)
                if not os.path.isfile(path_modules):
                    for module in os.scandir(path_modules):
                        if module.is_file() and module.path.endswith(".py"):
                            module_path = module.path
                            module_name = Path(module.path).stem

                            spec = importlib.util.spec_from_file_location(
                                module_name, module_path
                            )
                            module = importlib.util.module_from_spec(spec)
                            sys.modules[module_name] = module
                            spec.loader.exec_module(module)

                            dict_module: dict = module.get_dict_modules()
                            dict_modules = dict_modules | dict_module

                else:
                    spec = importlib.util.spec_from_file_location(
                        module_name, path_modules
                    )
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)

                    dict_modules: dict = module.get_dict_modules()

            kwargs = dict_model | dict_modules

            self.logger.debug("Template Render Arguments: %s" % str(kwargs))

            # Remove old template from directory
            self.__delete_template(path_template=_path_template_destination)

            for template_path in ls_templates_source:
                # _path_template_source = os.path.abspath(template_path)
                _path_template = os.path.relpath(template_path, path_template_source)
                _path_template = _path_template.replace("\\", "/")

                self.logger.debug(
                    f"Start generating output for template: {_path_template}"
                )

                # # Check for valid input path
                if not os.path.exists(template_path):
                    self.__error_handler(f"Source Path does not exist {template_path}")

                if not len(self.get_errors()):
                    try:
                        template_file_path: str = ""
                        # with open(_path_template) as file_:
                        # template = Template(file_.read())
                        template = templateEnv.get_template(_path_template)
                        template_file_path = template.filename
                        template_name = os.path.basename(template_file_path)

                        self.logger.debug(f"Start generating Template: {template_name}")

                        __output = template.render(**kwargs)

                        # Write output to file
                        self.write_output(
                            input_file_name=template_name,
                            output=__output,
                            path_template_destination=_path_template_destination,
                        )

                        self.logger.info(
                            f"Finished generating output for template: {_path_template}"
                        )

                    except jinja2.TemplateSyntaxError as e:
                        msg = textwrap.dedent(
                            """
                            Error Generating Output!
                            --------------------------
                            Template:   {}
                            Error:      {}
                            Error-Type: {}
                            Error_Line: {}

                            An error occurred rendering the template with the context
                            parameters
                        """.format(
                                template_file_path, e, type(e).__name__, e.lineno
                            )
                        )

                        self.__error_handler(msg)

                    except Exception as e:
                        tb = e.__traceback__

                        traceback_summary = []
                        template_error_line = -1

                        while tb:
                            if "template" in tb.tb_frame.f_code.co_name:
                                template_error_line = tb.tb_lineno

                            traceback_summary.append(
                                "%s at %s:%s"
                                % (
                                    tb.tb_frame.f_code.co_name,
                                    tb.tb_frame.f_code.co_filename,
                                    tb.tb_lineno,
                                )
                            )
                            tb = tb.tb_next

                        msg = textwrap.dedent(
                            """

                            Error Generating Output!
                            --------------------------
                            Template:   %(template_path)s
                            Error:      %(error_message)s
                            Error-Type: %(error_type)s
                            Error-Line: %(error_line)s

                            An error occurred rendering the template with the context
                            parameters

                            Traceback
                            --------------------------
                        """
                            % {
                                "template_path": template_file_path,
                                "error_message": e,
                                "error_type": type(e).__name__,
                                "error_line": template_error_line,
                            }
                        )

                        # seperatly added to keep a consistent indentation level
                        msg += "\n".join(traceback_summary)

                        self.__error_handler(msg)

                else:
                    self.logger.error("Templates not created due to prior error")

        except Exception as e:
            self.__error_handler(str(e))
