from pytest_cases import parametrize


class CasesPropertyValueResolution:
    @parametrize(
        "input",
        [
            (
                "jobs/sales_weekly",
                [
                    "jobs/sales_weekly",
                    "schedules/weekly",
                    "cluster/extra_small",
                ],
            )
        ],
    )
    def case_property_values_valid(self, input):
        return input
