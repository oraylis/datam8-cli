"""Persisted mapping repositories for legacy source-port unit fixtures."""

from types import SimpleNamespace

from datam8_model.data_source import SourceDataTypeMapping


def configure_mappings(model):
    mappings = [
        SourceDataTypeMapping(sourceType=name, targetType="string")
        for name in ("varchar", "string", "int")
    ]
    model.dataSources = {
        name: SimpleNamespace(entity=SimpleNamespace(type="Test", dataTypeMapping=None))
        for name in ("crm", "test")
    }
    model.dataSourceTypes = {
        "Test": SimpleNamespace(entity=SimpleNamespace(dataTypeMapping=mappings))
    }
    return model
