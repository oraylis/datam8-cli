from typing import Dict, Type, Optional, List
import logging

from .BaseSourceConnector import BaseSourceConnector, ConnectionInfo

logger = logging.getLogger(__name__)


class ConnectorRegistry:
    """
    Registry for managing source connector plugins.
    
    This class provides a centralized mechanism for registering and instantiating
    source connector plugins that implement the BaseSourceConnector interface.
    """
    
    _instance: Optional['ConnectorRegistry'] = None
    _connectors: Dict[str, Type[BaseSourceConnector]] = {}
    
    def __new__(cls) -> 'ConnectorRegistry':
        """Implement singleton pattern for the registry."""
        if cls._instance is None:
            cls._instance = super(ConnectorRegistry, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize the connector registry."""
        if not hasattr(self, 'initialized'):
            self.logger = logging.getLogger(self.__class__.__name__)
            self.initialized = True
            self._auto_discover_connectors()
    
    def register_connector(self, source_type: str, connector_class: Type[BaseSourceConnector]) -> None:
        """
        Register a connector class for a specific source type.
        
        Args:
            source_type (str): The source type identifier (e.g., 'SqlDataSource', 'LakeSource')
            connector_class (Type[BaseSourceConnector]): The connector class to register
            
        Raises:
            ValueError: If the connector class doesn't inherit from BaseSourceConnector
        """
        if not issubclass(connector_class, BaseSourceConnector):
            raise ValueError(f"Connector class {connector_class.__name__} must inherit from BaseSourceConnector")
        
        if source_type in self._connectors:
            self.logger.warning(f"Overriding existing connector for source type '{source_type}'")
        
        self._connectors[source_type] = connector_class
        self.logger.info(f"Registered connector {connector_class.__name__} for source type '{source_type}'")
    
    def get_connector_class(self, source_type: str) -> Optional[Type[BaseSourceConnector]]:
        """
        Get the connector class for a specific source type.
        
        Args:
            source_type (str): The source type identifier
            
        Returns:
            Optional[Type[BaseSourceConnector]]: The connector class or None if not found
        """
        return self._connectors.get(source_type)
    
    def create_connector(self, connection_info: ConnectionInfo, 
                        log_level: int = logging.INFO) -> Optional[BaseSourceConnector]:
        """
        Create a connector instance for the given connection info.
        
        Args:
            connection_info (ConnectionInfo): Connection details for the data source
            log_level (int): Logging level for the connector
            
        Returns:
            Optional[BaseSourceConnector]: The connector instance or None if no suitable connector found
            
        Raises:
            RuntimeError: If connector instantiation fails
        """
        connector_class = self.get_connector_class(connection_info.data_source_type)
        
        if connector_class is None:
            self.logger.error(f"No connector found for source type '{connection_info.data_source_type}'")
            return None
        
        try:
            connector = connector_class(connection_info, log_level)
            self.logger.info(f"Created connector {connector_class.__name__} for '{connection_info.data_source_name}'")
            return connector
        except Exception as e:
            error_msg = f"Failed to create connector for '{connection_info.data_source_name}': {str(e)}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def get_available_source_types(self) -> List[str]:
        """
        Get a list of all registered source types.
        
        Returns:
            List[str]: List of source type identifiers
        """
        return list(self._connectors.keys())
    
    def get_connector_info(self) -> Dict[str, str]:
        """
        Get information about all registered connectors.
        
        Returns:
            Dict[str, str]: Mapping of source_type -> connector_class_name
        """
        return {source_type: connector_class.__name__ 
                for source_type, connector_class in self._connectors.items()}
    
    def _auto_discover_connectors(self) -> None:
        """
        Automatically discover and register connectors in the current module and connectors subdirectory.
        """
        # Auto-discover connectors
        
        
        # Manually register known connectors to ensure they are available
        try:
            from .SqlServerConnector import SqlServerConnector
            if 'SqlDataSource' not in self._connectors:
                self.register_connector('SqlDataSource', SqlServerConnector)
        except ImportError as e:
            self.logger.debug(f"Could not import SqlServerConnector: {e}")
        
        try:
            from .OracleConnector import OracleConnector
            if 'OracleDataSource' not in self._connectors:
                self.register_connector('OracleDataSource', OracleConnector)
        except ImportError as e:
            self.logger.debug(f"Could not import OracleConnector: {e}")
        
    


# Global registry instance
registry = ConnectorRegistry()


def register_connector(source_type: str, connector_class: Type[BaseSourceConnector]) -> None:
    """
    Convenience function to register a connector with the global registry.
    
    Args:
        source_type (str): The source type identifier
        connector_class (Type[BaseSourceConnector]): The connector class to register
    """
    registry.register_connector(source_type, connector_class)


def get_connector(connection_info: ConnectionInfo, 
                 log_level: int = logging.INFO) -> Optional[BaseSourceConnector]:
    """
    Convenience function to create a connector from the global registry.
    
    Args:
        connection_info (ConnectionInfo): Connection details for the data source
        log_level (int): Logging level for the connector
        
    Returns:
        Optional[BaseSourceConnector]: The connector instance or None if not found
    """
    return registry.create_connector(connection_info, log_level)