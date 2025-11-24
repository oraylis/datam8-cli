import json
import pathlib

from dm8model_v1 import (
    CoreModelEntry,
    CuratedModelEntry,
    RawModelEntry,
    StageModelEntry,
    Solution,
)

type ModelEntitiesType = (
    RawModelEntry.Model
    | StageModelEntry.Model
    | CoreModelEntry.Model
    | CuratedModelEntry.Model
)


def parse_solution_file(solution_file_path: pathlib.Path) -> Solution.Model:
    return Solution.Model.from_json_file(solution_file_path)


def read_type(file_path: pathlib.Path) -> type[ModelEntitiesType]:
    _type: str = json.loads(file_path.read_bytes())["type"].upper()

    match _type:
        case _ if _type in RawModelEntry.Type._member_names_:
            return RawModelEntry.Model
        case _ if _type in StageModelEntry.Type._member_names_:
            return StageModelEntry.Model
        case _ if _type in CoreModelEntry.Type._member_names_:
            return CoreModelEntry.Model
        case _ if _type in RawModelEntry.Type._member_names_:
            return CuratedModelEntry.Model

    raise Exception("Unknown type: %s", _type)


def parse_model_file(model_file_path: pathlib.Path) -> ModelEntitiesType:
    _type = read_type(model_file_path)

    match _type:
        case RawModelEntry.Model:
            return RawModelEntry.Model.from_json_file(model_file_path)
        case StageModelEntry.Model:
            return StageModelEntry.Model.from_json_file(model_file_path)
        case CoreModelEntry.Model:
            return CoreModelEntry.Model.from_json_file(model_file_path)
        case CuratedModelEntry.Model:
            return CuratedModelEntry.Model.from_json_file(model_file_path)
