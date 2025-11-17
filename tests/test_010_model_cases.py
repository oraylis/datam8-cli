from pytest_cases import parametrize


class CasesLayer:
    @parametrize("layer", ["stage", "core", "curated"])
    def case_layer_valid(self, layer):
        return layer


class CasesLocator:
    @parametrize(
        "locator",
        [
            "attributeTypes/Generic Int",
            "dataProducts/Sales",
            "dataSources/AdventureWorks",
            "dataSourceTypes/SqlDataSource",
            "dataTypes/string",
            "properties/jobs",
            "zones/raw",
            "folders/020-Core/Sales",
        ],
    )
    def case_locator_valid(self, locator):
        return locator

    @parametrize(
        "locator",
        [
            "//Sales/Product/Product",
            "/010-staging",
            "|010-staging|Sales|Product|Product",
        ],
    )
    def case_locator_invalid(self, locator):
        return locator

    def case_locator_multiple(self):
        return "dataProducts/"

    def case_locator_unkown(self):
        return "/010-staging/Sales/Delivery/Product"

    # fmt: off
    @parametrize(
        "test_case",
        [
            # tuple-format (left side, right side, expected result
            ("dataProducts/Sales", "dataProducts/", True),
            ("dataProducts/Sales", "dataProducts/Sales", True),
            ("properties/jobs", "propertyValues/", False),
            ("modelEntities/Sales/Customer/Customer", "modelEntities/Sales/", True),
            ("modelEntities/Sales/Customer/", "modelEntities/Sales/", True),
        ],
    )
    # fmt: on
    def case_locator_comparison(self, test_case):
        return test_case


class CasesModel:
    @parametrize(
        "attribute",
        [
            "modelEntities",
            "properties",
            "dataSources",
        ],
    )
    def case_model_attributes(self, attribute):
        return attribute

    @parametrize(
        "function",
        [
            "get_data_type",
            "get_data_source",
        ],
    )
    def case_model_functions(self, function):
        return function


class CasesEntityLookup:
    @parametrize(
        "input",
        [
            ("dataTypes", ["string", "money"]),
            ("attributeTypes", ["Amt", "BirthDate"]),
            ("zones", ["raw", "core"]),
            ("properties", ["jobs"]),
            ("dataSources", ["AdventureWorks"]),
            ("dataSourceTypes", ["SqlDataSource"]),
            ("dataProducts", ["Sales"]),
            ("dataModules", ["Sales/Other"]),
        ],
    )
    def case_get_entity_dict_valid(self, input):
        return input
