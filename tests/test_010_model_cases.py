from pytest_cases import parametrize


class CasesLayer:
    @parametrize("layer", ["stage", "core", "curated"])
    def case_layer_valid(self, layer):
        return layer


class CasesLocator:
    @parametrize(
        "locator",
        [
            # tuple consisting of a zone name and a valid locator
            ("stage", "/010-staging/Sales/Product/Product"),
            ("stage", "/010-staging/Sales/Customer/Customer_DE"),
            ("core", "/020-core/Sales/Customer/Customer"),
            ("curated", "/030-curated/Sales/Customer/DimCustomer"),
            ("curated", "/030-curated/Sales/Customer/DimCustomer"),
            ("curated", "030-curated/Sales/Customer/DimCustomer"),
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
        return "/"

    def case_locator_unkown(self):
        return "/010-staging/Sales/Delivery/Product"


class CasesModel:
    @parametrize(
        "attribute",
        [
            "lookup_entity",
            "perform_initial_checks",
        ],
    )
    def case_model_attributes(self, attribute):
        return attribute
