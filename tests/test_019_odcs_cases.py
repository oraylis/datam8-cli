"""Independent contracts for exercising ODCS 3.2 field mapping."""


def contract(properties=None, **changes):
    result = {
        "apiVersion": "v3.2.0",
        "kind": "DataContract",
        "version": "1.0.0",
        "id": "test-contract",
        "schema": [
            {
                "name": "customers",
                "properties": properties or [{"name": "id", "logicalType": "integer"}],
            }
        ],
    }
    result.update(changes)
    return result


class CasesOdcsTypes:
    def case_string(self):
        return {"name": "value", "logicalType": "string"}, "string"

    def case_integer(self):
        return {"name": "value", "logicalType": "integer"}, "long"

    def case_number(self):
        return {"name": "value", "logicalType": "number"}, "decimal"

    def case_boolean(self):
        return {"name": "value", "logicalType": "boolean"}, "bit"

    def case_date(self):
        return {"name": "value", "logicalType": "date"}, "date"

    def case_timestamp(self):
        return {"name": "value", "logicalType": "timestamp"}, "datetime"

    def case_time(self):
        return {"name": "value", "logicalType": "time"}, "time"

    def case_object(self):
        return {
            "name": "value",
            "logicalType": "object",
            "properties": [{"name": "child", "logicalType": "string"}],
        }, "string"

    def case_array(self):
        return {
            "name": "value",
            "logicalType": "array",
            "items": {"logicalType": "string"},
        }, "string"

    def case_map(self):
        return {
            "name": "value",
            "logicalType": "map",
            "map": {"key": {"logicalType": "string"}, "value": {"logicalType": "integer"}},
        }, "string"

    def case_vector(self):
        return {
            "name": "value",
            "logicalType": "vector",
            "logicalTypeOptions": {"dimensions": 1536},
        }, "string"

    def case_unknown_physical(self):
        return {"name": "value", "physicalType": "VendorType", "logicalType": "integer"}, None

    def case_physical_override(self):
        return {"name": "value", "physicalType": "DOUBLE", "logicalType": "number"}, "double"

    def case_physical_only(self):
        return {"name": "value", "physicalType": "VARCHAR(40)"}, "string"

    def case_signed_format(self):
        return {
            "name": "value",
            "logicalType": "integer",
            "logicalTypeOptions": {"format": "i16"},
        }, "long"

    def case_unsigned_format(self):
        return {
            "name": "value",
            "logicalType": "integer",
            "logicalTypeOptions": {"format": "u64"},
        }, "long"

    def case_float_format(self):
        return {
            "name": "value",
            "logicalType": "number",
            "logicalTypeOptions": {"format": "f32"},
        }, "decimal"
