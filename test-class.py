from src.dm8model.base import BaseEntity, EntityType
from src.dm8model.model import ModelEntity
from pathlib import Path
import json
import os

base_entities: dict[str, list[BaseEntity]] = {}
base_file_path = Path("%s/Base/" % os.environ["DATAM8_SOLUTION_PATH"])

model_entities: list[ModelEntity] = []
model_file_path = Path("%s/Model/" % os.environ["DATAM8_SOLUTION_PATH"])

for file in [*base_file_path.glob("**/*.json"),*model_file_path.glob("**/.properties.json")]:
    print("Parsing %s" % file)
    with open(file, "r") as f:
        entity = BaseEntity.model_validate_json(f.read())
        base_entities[entity.root.type] = getattr(entity.root, entity.root.type)

for e in base_entities.values():
    for s in e:
        print(s.name)

for file in model_file_path.glob("**/*.json"):
    if file.match("*.properties.json"):
        continue

    with open(file, "r") as f:
        try:
            entity = ModelEntity.model_validate_json(f.read())
            model_entities.append(entity)
        except Exception as e:
            print("Error parsing %s" % file)
            raise e


for m in model_entities:
    print(m.name, m.displayName, len(m.attributes))

# print(json.dumps(json.loads(model_entities[-1].model_dump_json()), indent=4))
print(
    json.dumps(
        json.loads(
            base_entities[EntityType.FOLDERS.value][0].model_dump_json()
        ),
        indent=4,
    )
)
