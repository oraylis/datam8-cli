from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ColumnMetadata:
    """Represents metadata for a database column."""
    
    name: str
    data_type: str
    is_nullable: bool
    ordinal_position: int
    character_maximum_length: Optional[int] = None
    numeric_precision: Optional[int] = None
    numeric_scale: Optional[int] = None
    is_primary_key: bool = False
    is_foreign_key: bool = False
    is_unique: bool = False
    default_value: Optional[str] = None


@dataclass
class TableMetadata:
    """Represents metadata for a database table."""
    
    schema_name: str
    table_name: str
    table_type: str
    columns: List[ColumnMetadata]
    primary_keys: List[str]
    foreign_keys: Dict[str, str]  # column_name -> referenced_table
    unique_constraints: List[List[str]]  # list of unique constraint column groups


@dataclass
class ConnectionInfo:
    """Represents connection information for a data source."""
    
    data_source_name: str
    data_source_type: str
    connection_string: str
    extended_properties: Dict[str, Any]


class BaseSourceConnector(ABC):
    """
    Abstract base class for all source connectors in the DataM8 reverse generator.
    
    This class defines the interface that all source connectors must implement
    to enable the plugin-based architecture for discovering metadata from 
    various data sources.
    """

    def __init__(self, connection_info: ConnectionInfo, log_level: int = logging.INFO):
        """
        Initialize the source connector.
        
        Args:
            connection_info (ConnectionInfo): Connection details for the data source
            log_level (int): Logging level for the connector
        """
        self.connection_info = connection_info
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(log_level)
        self._connection = None

    @property
    def source_type(self) -> str:
        """Return the source type identifier for this connector."""
        return self.connection_info.data_source_type

    @property
    def source_name(self) -> str:
        """Return the source name for this connector."""
        return self.connection_info.data_source_name

    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to the data source.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """
        Close connection to the data source.
        
        Returns:
            bool: True if disconnection successful, False otherwise
        """
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """
        Test the connection to the data source without establishing a persistent connection.
        
        Returns:
            bool: True if connection test successful, False otherwise
        """
        pass

    @abstractmethod
    def discover_tables(self, schema_filter: Optional[str] = None, 
                       table_filter: Optional[List[str]] = None) -> List[str]:
        """
        Discover available tables in the data source.
        
        Args:
            schema_filter (Optional[str]): Filter tables by schema name
            table_filter (Optional[List[str]]): Filter by specific table names
            
        Returns:
            List[str]: List of fully qualified table names (schema.table)
        """
        pass

    @abstractmethod
    def get_table_metadata(self, table_name: str, schema_name: Optional[str] = None) -> TableMetadata:
        """
        Get comprehensive metadata for a specific table.
        
        Args:
            table_name (str): Name of the table
            schema_name (Optional[str]): Schema name (if not included in table_name)
            
        Returns:
            TableMetadata: Complete metadata for the table
        """
        pass

    @abstractmethod
    def get_column_metadata(self, table_name: str, schema_name: Optional[str] = None) -> List[ColumnMetadata]:
        """
        Get metadata for all columns in a specific table.
        
        Args:
            table_name (str): Name of the table
            schema_name (Optional[str]): Schema name (if not included in table_name)
            
        Returns:
            List[ColumnMetadata]: List of column metadata
        """
        pass

    @abstractmethod
    def get_primary_keys(self, table_name: str, schema_name: Optional[str] = None) -> List[str]:
        """
        Get primary key columns for a specific table.
        
        Args:
            table_name (str): Name of the table
            schema_name (Optional[str]): Schema name (if not included in table_name)
            
        Returns:
            List[str]: List of primary key column names
        """
        pass

    @abstractmethod
    def get_foreign_keys(self, table_name: str, schema_name: Optional[str] = None) -> Dict[str, str]:
        """
        Get foreign key relationships for a specific table.
        
        Args:
            table_name (str): Name of the table
            schema_name (Optional[str]): Schema name (if not included in table_name)
            
        Returns:
            Dict[str, str]: Mapping of column_name -> referenced_table
        """
        pass

    @abstractmethod
    def get_unique_constraints(self, table_name: str, schema_name: Optional[str] = None) -> List[List[str]]:
        """
        Get unique constraints for a specific table.
        
        Args:
            table_name (str): Name of the table
            schema_name (Optional[str]): Schema name (if not included in table_name)
            
        Returns:
            List[List[str]]: List of unique constraint column groups
        """
        pass

    def __enter__(self):
        """Context manager entry - establish connection."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close connection."""
        self.disconnect()
        return False

    def _parse_table_name(self, table_name: str) -> tuple[Optional[str], str]:
        """
        Parse a potentially qualified table name into schema and table components.
        
        Args:
            table_name (str): Table name, potentially including schema
            
        Returns:
            tuple[Optional[str], str]: (schema_name, table_name)
        """
        if '.' in table_name:
            parts = table_name.split('.')
            if len(parts) == 2:
                return parts[0], parts[1]
            elif len(parts) > 2:
                # Handle cases like [schema].[table] or database.schema.table
                return '.'.join(parts[:-1]), parts[-1]
        return None, table_name

    def _error_handler(self, error: Exception, context: str = "") -> None:
        """
        Handle errors with consistent logging.
        
        Args:
            error (Exception): The error that occurred
            context (str): Additional context about where the error occurred
        """
        error_msg = f"Error in {self.__class__.__name__}"
        if context:
            error_msg += f" during {context}"
        error_msg += f": {str(error)}"
        
        self.logger.error(error_msg)
        raise RuntimeError(error_msg) from error