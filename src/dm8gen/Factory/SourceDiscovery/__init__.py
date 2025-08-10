"""
Source Discovery module for DataM8 Reverse Generator.

This module provides the plugin-based architecture for discovering
metadata from various data sources like SQL Server, Oracle, ADLS, etc.
"""

from .BaseSourceConnector import BaseSourceConnector, ConnectionInfo
from .ConnectorRegistry import ConnectorRegistry, get_connector
from .SqlServerConnector import SqlServerConnector
from .OracleConnector import OracleConnector

__all__ = [
    'BaseSourceConnector',
    'ConnectionInfo',
    'ConnectorRegistry', 
    'SqlServerConnector',
    'OracleConnector',
    'get_connector'
]