from typing import Dict, List, Optional, Any
import logging
import re
from urllib.parse import urlparse, parse_qs

from .BaseSourceConnector import BaseSourceConnector, ColumnMetadata, TableMetadata, ConnectionInfo

logger = logging.getLogger(__name__)


class SqlServerConnector(BaseSourceConnector):
    """
    SQL Server connector for discovering table and column metadata.
    
    This connector uses INFORMATION_SCHEMA views and system tables to extract
    metadata from SQL Server databases.
    """
    
    SOURCE_TYPE = "SqlDataSource"
    
    def __init__(self, connection_info: ConnectionInfo, log_level: int = logging.INFO):
        """
        Initialize SQL Server connector.
        
        Args:
            connection_info (ConnectionInfo): SQL Server connection details
            log_level (int): Logging level
        """
        super().__init__(connection_info, log_level)
        self._connection = None
        self._engine = None
    
    def connect(self) -> bool:
        """
        Establish connection to SQL Server.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            # Use SQLAlchemy with pymssql driver
            from sqlalchemy import create_engine, text
            
            # Use connection string directly (should be in SQLAlchemy format)
            self._engine = create_engine(self.connection_info.connection_string)
            self._connection = self._engine.connect()
            self.logger.info(f"Connected to SQL Server database using SQLAlchemy + pymssql")
            return True
                    
        except Exception as e:
            self.logger.error(f"Failed to connect to SQL Server: {str(e)}")
            return False
    
    def disconnect(self) -> bool:
        """
        Close connection to SQL Server.
        
        Returns:
            bool: True if disconnection successful, False otherwise
        """
        try:
            if self._connection:
                self._connection.close()
                self._connection = None
                
            if hasattr(self, '_engine') and self._engine:
                self._engine.dispose()
                self._engine = None
                
            self.logger.info("Disconnected from SQL Server database")
            return True
            
        except Exception as e:
            self.logger.error(f"Error disconnecting from SQL Server: {str(e)}")
            return False
    
    def test_connection(self) -> bool:
        """
        Test connection to SQL Server without establishing persistent connection.
        
        Returns:
            bool: True if connection test successful, False otherwise
        """
        try:
            if self.connect():
                result = self._execute_query("SELECT 1 as test")
                self.disconnect()
                return len(result) == 1 and result[0][0] == 1
            return False
            
        except Exception as e:
            self.logger.error(f"Connection test failed: {str(e)}")
            return False
    
    def discover_tables(self, schema_filter: Optional[str] = None, 
                       table_filter: Optional[List[str]] = None) -> List[str]:
        """
        Discover available tables in SQL Server database.
        
        Args:
            schema_filter (Optional[str]): Filter tables by schema name
            table_filter (Optional[List[str]]): Filter by specific table names
            
        Returns:
            List[str]: List of fully qualified table names (schema.table)
        """
        try:
            query = """
            SELECT TABLE_SCHEMA, TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_TYPE = 'BASE TABLE'
            """
            
            params = []
            
            if schema_filter:
                query += " AND TABLE_SCHEMA = ?"
                params.append(schema_filter)
            
            if table_filter:
                placeholders = ','.join(['?' for _ in table_filter])
                query += f" AND TABLE_NAME IN ({placeholders})"
                params.extend(table_filter)
            
            query += " ORDER BY TABLE_SCHEMA, TABLE_NAME"
            
            results = self._execute_query(query, params)
            
            tables = []
            for row in results:
                schema_name, table_name = row
                tables.append(f"{schema_name}.{table_name}")
            
            self.logger.info(f"Discovered {len(tables)} tables")
            return tables
            
        except Exception as e:
            self._error_handler(e, "table discovery")
            return []
    
    def get_table_metadata(self, table_name: str, schema_name: Optional[str] = None) -> TableMetadata:
        """
        Get comprehensive metadata for a specific table.
        
        Args:
            table_name (str): Name of the table
            schema_name (Optional[str]): Schema name (if not included in table_name)
            
        Returns:
            TableMetadata: Complete metadata for the table
        """
        try:
            parsed_schema, parsed_table = self._parse_table_name(table_name)
            if not parsed_schema and schema_name:
                parsed_schema = schema_name
            elif not parsed_schema:
                parsed_schema = 'dbo'  # Default schema
            
            # Get column metadata
            columns = self.get_column_metadata(parsed_table, parsed_schema)
            
            # Get primary keys
            primary_keys = self.get_primary_keys(parsed_table, parsed_schema)
            
            # Get foreign keys
            foreign_keys = self.get_foreign_keys(parsed_table, parsed_schema)
            
            # Get unique constraints
            unique_constraints = self.get_unique_constraints(parsed_table, parsed_schema)
            
            return TableMetadata(
                schema_name=parsed_schema,
                table_name=parsed_table,
                table_type='BASE TABLE',
                columns=columns,
                primary_keys=primary_keys,
                foreign_keys=foreign_keys,
                unique_constraints=unique_constraints
            )
            
        except Exception as e:
            self._error_handler(e, f"getting table metadata for {table_name}")
    
    def get_column_metadata(self, table_name: str, schema_name: Optional[str] = None) -> List[ColumnMetadata]:
        """
        Get metadata for all columns in a specific table.
        
        Args:
            table_name (str): Name of the table
            schema_name (Optional[str]): Schema name
            
        Returns:
            List[ColumnMetadata]: List of column metadata
        """
        try:
            parsed_schema, parsed_table = self._parse_table_name(table_name)
            if not parsed_schema and schema_name:
                parsed_schema = schema_name
            elif not parsed_schema:
                parsed_schema = 'dbo'
            
            query = """
            SELECT 
                COLUMN_NAME,
                DATA_TYPE,
                IS_NULLABLE,
                CHARACTER_MAXIMUM_LENGTH,
                NUMERIC_PRECISION,
                NUMERIC_SCALE,
                ORDINAL_POSITION,
                COLUMN_DEFAULT
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION
            """
            
            results = self._execute_query(query, [parsed_schema, parsed_table])
            
            # Get constraint information
            primary_keys = set(self.get_primary_keys(parsed_table, parsed_schema))
            foreign_keys = set(self.get_foreign_keys(parsed_table, parsed_schema).keys())
            unique_constraints_flat = set()
            for constraint in self.get_unique_constraints(parsed_table, parsed_schema):
                unique_constraints_flat.update(constraint)
            
            columns = []
            for row in results:
                col_name, data_type, is_nullable_str, char_len, num_precision, num_scale, ordinal, default_val = row
                
                columns.append(ColumnMetadata(
                    name=col_name,
                    data_type=data_type,
                    is_nullable=is_nullable_str.upper() == 'YES',
                    ordinal_position=ordinal,
                    character_maximum_length=char_len,
                    numeric_precision=num_precision,
                    numeric_scale=num_scale,
                    is_primary_key=col_name in primary_keys,
                    is_foreign_key=col_name in foreign_keys,
                    is_unique=col_name in unique_constraints_flat,
                    default_value=default_val
                ))
            
            self.logger.info(f"Retrieved {len(columns)} columns for table {parsed_schema}.{parsed_table}")
            return columns
            
        except Exception as e:
            self._error_handler(e, f"getting column metadata for {table_name}")
            return []
    
    def get_primary_keys(self, table_name: str, schema_name: Optional[str] = None) -> List[str]:
        """
        Get primary key columns for a specific table.
        
        Args:
            table_name (str): Name of the table
            schema_name (Optional[str]): Schema name
            
        Returns:
            List[str]: List of primary key column names
        """
        try:
            parsed_schema, parsed_table = self._parse_table_name(table_name)
            if not parsed_schema and schema_name:
                parsed_schema = schema_name
            elif not parsed_schema:
                parsed_schema = 'dbo'
            
            query = """
            SELECT kcu.COLUMN_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
            JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc 
                ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
            WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                AND kcu.TABLE_SCHEMA = ? 
                AND kcu.TABLE_NAME = ?
            ORDER BY kcu.ORDINAL_POSITION
            """
            
            results = self._execute_query(query, [parsed_schema, parsed_table])
            return [row[0] for row in results]
            
        except Exception as e:
            self._error_handler(e, f"getting primary keys for {table_name}")
            return []
    
    def get_foreign_keys(self, table_name: str, schema_name: Optional[str] = None) -> Dict[str, str]:
        """
        Get foreign key relationships for a specific table.
        
        Args:
            table_name (str): Name of the table
            schema_name (Optional[str]): Schema name
            
        Returns:
            Dict[str, str]: Mapping of column_name -> referenced_table
        """
        try:
            parsed_schema, parsed_table = self._parse_table_name(table_name)
            if not parsed_schema and schema_name:
                parsed_schema = schema_name
            elif not parsed_schema:
                parsed_schema = 'dbo'
            
            query = """
            SELECT 
                kcu1.COLUMN_NAME,
                kcu2.TABLE_SCHEMA + '.' + kcu2.TABLE_NAME AS REFERENCED_TABLE
            FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu1
                ON rc.CONSTRAINT_NAME = kcu1.CONSTRAINT_NAME
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu2
                ON rc.UNIQUE_CONSTRAINT_NAME = kcu2.CONSTRAINT_NAME
            WHERE kcu1.TABLE_SCHEMA = ? AND kcu1.TABLE_NAME = ?
            """
            
            results = self._execute_query(query, [parsed_schema, parsed_table])
            return {row[0]: row[1] for row in results}
            
        except Exception as e:
            self._error_handler(e, f"getting foreign keys for {table_name}")
            return {}
    
    def get_unique_constraints(self, table_name: str, schema_name: Optional[str] = None) -> List[List[str]]:
        """
        Get unique constraints for a specific table.
        
        Args:
            table_name (str): Name of the table
            schema_name (Optional[str]): Schema name
            
        Returns:
            List[List[str]]: List of unique constraint column groups
        """
        try:
            parsed_schema, parsed_table = self._parse_table_name(table_name)
            if not parsed_schema and schema_name:
                parsed_schema = schema_name
            elif not parsed_schema:
                parsed_schema = 'dbo'
            
            query = """
            SELECT 
                tc.CONSTRAINT_NAME,
                kcu.COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
            WHERE tc.CONSTRAINT_TYPE = 'UNIQUE'
                AND tc.TABLE_SCHEMA = ? 
                AND tc.TABLE_NAME = ?
            ORDER BY tc.CONSTRAINT_NAME, kcu.ORDINAL_POSITION
            """
            
            results = self._execute_query(query, [parsed_schema, parsed_table])
            
            # Group columns by constraint name
            constraints = {}
            for constraint_name, column_name in results:
                if constraint_name not in constraints:
                    constraints[constraint_name] = []
                constraints[constraint_name].append(column_name)
            
            return list(constraints.values())
            
        except Exception as e:
            self._error_handler(e, f"getting unique constraints for {table_name}")
            return []
    
    def _execute_query(self, query: str, params: Optional[List[Any]] = None) -> List[tuple]:
        """
        Execute a SQL query and return results.
        
        Args:
            query (str): SQL query to execute
            params (Optional[List[Any]]): Query parameters
            
        Returns:
            List[tuple]: Query results
        """
        try:
            # Using SQLAlchemy only
            from sqlalchemy import text
            if params:
                # Convert positional parameters to dictionary for SQLAlchemy 2.x
                # Replace ? placeholders with named parameters
                named_query = query
                param_dict = {}
                for i, param in enumerate(params):
                    placeholder = f":param{i}"
                    named_query = named_query.replace("?", placeholder, 1)
                    param_dict[f"param{i}"] = param
                result = self._connection.execute(text(named_query), param_dict)
            else:
                result = self._connection.execute(text(query))
            return result.fetchall()
                
        except Exception as e:
            self.logger.error(f"Query execution failed: {str(e)}")
            self.logger.debug(f"Query: {query}")
            self.logger.debug(f"Params: {params}")
            raise
    
