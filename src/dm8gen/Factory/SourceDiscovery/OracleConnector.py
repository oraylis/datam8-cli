from typing import Dict, List, Optional
import logging

from .BaseSourceConnector import BaseSourceConnector, ColumnMetadata, TableMetadata, ConnectionInfo

logger = logging.getLogger(__name__)


class OracleConnector(BaseSourceConnector):
    """
    Oracle Database connector for discovering table and column metadata.
    
    This connector uses Oracle data dictionary views to extract
    metadata from Oracle databases.
    """
    
    SOURCE_TYPE = "OracleDataSource"
    
    def __init__(self, connection_info: ConnectionInfo, log_level: int = logging.INFO):
        """
        Initialize Oracle connector.
        
        Args:
            connection_info (ConnectionInfo): Oracle connection details
            log_level (int): Logging level
        """
        super().__init__(connection_info, log_level)
        self._connection = None
        self._engine = None
    
    def connect(self) -> bool:
        """
        Establish connection to Oracle database.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            # Use SQLAlchemy with Oracle driver
            from sqlalchemy import create_engine
            
            # Parse Oracle connection string and convert to SQLAlchemy format
            oracle_url = self._parse_oracle_connection_string()
            
            self._engine = create_engine(oracle_url)
            self._connection = self._engine.connect()
            self.logger.info("Connected to Oracle database using SQLAlchemy")
            return True
                    
        except Exception as e:
            self.logger.error(f"Failed to connect to Oracle: {str(e)}")
            return False
    
    def disconnect(self) -> bool:
        """
        Close connection to Oracle database.
        
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
                
            self.logger.info("Disconnected from Oracle database")
            return True
            
        except Exception as e:
            self.logger.error(f"Error disconnecting from Oracle: {str(e)}")
            return False
    
    def test_connection(self) -> bool:
        """
        Test connection to Oracle database without establishing persistent connection.
        
        Returns:
            bool: True if connection test successful, False otherwise
        """
        try:
            if self.connect():
                result = self._execute_query("SELECT 1 FROM DUAL")
                self.disconnect()
                return len(result) == 1 and result[0][0] == 1
            return False
            
        except Exception as e:
            self.logger.error(f"Connection test failed: {str(e)}")
            return False
    
    def discover_tables(self, schema_filter: Optional[str] = None, 
                       table_filter: Optional[List[str]] = None) -> List[str]:
        """
        Discover available tables in Oracle database.
        
        Args:
            schema_filter (Optional[str]): Filter tables by schema name
            table_filter (Optional[List[str]]): Filter by specific table names
            
        Returns:
            List[str]: List of fully qualified table names (schema.table)
        """
        try:
            query = """
            SELECT OWNER, TABLE_NAME
            FROM ALL_TABLES 
            WHERE 1=1
            """
            
            params = []
            
            if schema_filter:
                query += " AND UPPER(OWNER) = UPPER(:schema_param)"
                params.append(('schema_param', schema_filter))
            
            if table_filter:
                # Create placeholders for table names
                table_placeholders = []
                for i, table in enumerate(table_filter):
                    param_name = f'table_param_{i}'
                    table_placeholders.append(f':{param_name}')
                    params.append((param_name, table.upper()))
                
                query += f" AND UPPER(TABLE_NAME) IN ({','.join(table_placeholders)})"
            
            query += " ORDER BY OWNER, TABLE_NAME"
            
            results = self._execute_query(query, params)
            
            tables = []
            for row in results:
                owner, table_name = row
                tables.append(f"{owner}.{table_name}")
            
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
                # Get current user as default schema
                current_user_result = self._execute_query("SELECT USER FROM DUAL")
                parsed_schema = current_user_result[0][0] if current_user_result else 'USER'
            
            # Ensure uppercase for Oracle
            parsed_schema = parsed_schema.upper()
            parsed_table = parsed_table.upper()
            
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
                table_type='TABLE',
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
                current_user_result = self._execute_query("SELECT USER FROM DUAL")
                parsed_schema = current_user_result[0][0] if current_user_result else 'USER'
            
            # Ensure uppercase for Oracle
            parsed_schema = parsed_schema.upper()
            parsed_table = parsed_table.upper()
            
            query = """
            SELECT 
                COLUMN_NAME,
                DATA_TYPE,
                NULLABLE,
                CHAR_LENGTH,
                DATA_PRECISION,
                DATA_SCALE,
                COLUMN_ID,
                DATA_DEFAULT
            FROM ALL_TAB_COLUMNS 
            WHERE OWNER = :schema_param AND TABLE_NAME = :table_param
            ORDER BY COLUMN_ID
            """
            
            params = [('schema_param', parsed_schema), ('table_param', parsed_table)]
            results = self._execute_query(query, params)
            
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
                    data_type=data_type.lower(),  # Convert to lowercase for consistency
                    is_nullable=is_nullable_str.upper() == 'Y',
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
                current_user_result = self._execute_query("SELECT USER FROM DUAL")
                parsed_schema = current_user_result[0][0] if current_user_result else 'USER'
            
            # Ensure uppercase for Oracle
            parsed_schema = parsed_schema.upper()
            parsed_table = parsed_table.upper()
            
            query = """
            SELECT acc.COLUMN_NAME
            FROM ALL_CONSTRAINTS ac
            JOIN ALL_CONS_COLUMNS acc ON ac.CONSTRAINT_NAME = acc.CONSTRAINT_NAME
                AND ac.OWNER = acc.OWNER
            WHERE ac.CONSTRAINT_TYPE = 'P'
                AND ac.OWNER = :schema_param 
                AND ac.TABLE_NAME = :table_param
            ORDER BY acc.POSITION
            """
            
            params = [('schema_param', parsed_schema), ('table_param', parsed_table)]
            results = self._execute_query(query, params)
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
                current_user_result = self._execute_query("SELECT USER FROM DUAL")
                parsed_schema = current_user_result[0][0] if current_user_result else 'USER'
            
            # Ensure uppercase for Oracle
            parsed_schema = parsed_schema.upper()
            parsed_table = parsed_table.upper()
            
            query = """
            SELECT 
                acc1.COLUMN_NAME,
                ac_ref.OWNER || '.' || ac_ref.TABLE_NAME AS REFERENCED_TABLE
            FROM ALL_CONSTRAINTS ac
            JOIN ALL_CONS_COLUMNS acc1 ON ac.CONSTRAINT_NAME = acc1.CONSTRAINT_NAME
                AND ac.OWNER = acc1.OWNER
            JOIN ALL_CONSTRAINTS ac_ref ON ac.R_CONSTRAINT_NAME = ac_ref.CONSTRAINT_NAME
                AND ac.R_OWNER = ac_ref.OWNER
            WHERE ac.CONSTRAINT_TYPE = 'R'
                AND ac.OWNER = :schema_param
                AND ac.TABLE_NAME = :table_param
            """
            
            params = [('schema_param', parsed_schema), ('table_param', parsed_table)]
            results = self._execute_query(query, params)
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
                current_user_result = self._execute_query("SELECT USER FROM DUAL")
                parsed_schema = current_user_result[0][0] if current_user_result else 'USER'
            
            # Ensure uppercase for Oracle
            parsed_schema = parsed_schema.upper()
            parsed_table = parsed_table.upper()
            
            query = """
            SELECT 
                ac.CONSTRAINT_NAME,
                acc.COLUMN_NAME
            FROM ALL_CONSTRAINTS ac
            JOIN ALL_CONS_COLUMNS acc ON ac.CONSTRAINT_NAME = acc.CONSTRAINT_NAME
                AND ac.OWNER = acc.OWNER
            WHERE ac.CONSTRAINT_TYPE = 'U'
                AND ac.OWNER = :schema_param 
                AND ac.TABLE_NAME = :table_param
            ORDER BY ac.CONSTRAINT_NAME, acc.POSITION
            """
            
            params = [('schema_param', parsed_schema), ('table_param', parsed_table)]
            results = self._execute_query(query, params)
            
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
    
    def _parse_oracle_connection_string(self) -> str:
        """
        Parse Oracle connection string and convert to SQLAlchemy format.
        
        Example input: 
        "Host=datam80ora.westeurope.cloudapp.azure.com;Port=1521;ConnectionType=Service;Connection=datam8test;User=datam8"
        
        Example output:
        "oracle+oracledb://datam8:password@datam80ora.westeurope.cloudapp.azure.com:1521/datam8test"
        
        Returns:
            str: SQLAlchemy Oracle connection URL
        """
        try:
            # Parse connection string parameters
            params = {}
            for part in self.connection_info.connection_string.split(';'):
                if '=' in part:
                    key, value = part.split('=', 1)
                    params[key.strip()] = value.strip()
            
            host = params.get('Host', 'localhost')
            port = params.get('Port', '1521')
            service_name = params.get('Connection', 'XE')
            username = params.get('User', 'oracle')
            
            # Get password from extended properties
            password = self.connection_info.extended_properties.get('password', '')
            if not password and 'Password' in params:
                password = params['Password']
            
            # Construct SQLAlchemy Oracle URL using modern oracledb
            oracle_url = f"oracle+oracledb://{username}:{password}@{host}:{port}/{service_name}"
            
            self.logger.debug(f"Converted Oracle connection string to: oracle+oracledb://{username}:***@{host}:{port}/{service_name}")
            return oracle_url
            
        except Exception as e:
            self.logger.error(f"Failed to parse Oracle connection string: {str(e)}")
            raise ValueError(f"Invalid Oracle connection string format: {str(e)}")
    
    def _execute_query(self, query: str, params: Optional[List[tuple]] = None) -> List[tuple]:
        """
        Execute an Oracle SQL query and return results.
        
        Args:
            query (str): SQL query to execute
            params (Optional[List[tuple]]): Query parameters as list of (name, value) tuples
            
        Returns:
            List[tuple]: Query results
        """
        try:
            from sqlalchemy import text
            
            if params:
                # Convert list of tuples to dictionary for SQLAlchemy
                param_dict = dict(params)
                result = self._connection.execute(text(query), param_dict)
            else:
                result = self._connection.execute(text(query))
                
            return result.fetchall()
                
        except Exception as e:
            self.logger.error(f"Oracle query execution failed: {str(e)}")
            self.logger.debug(f"Query: {query}")
            self.logger.debug(f"Params: {params}")
            raise
    
    def _parse_table_name(self, table_name: str) -> tuple[Optional[str], str]:
        """
        Parse a potentially qualified Oracle table name into schema and table components.
        
        Handles Oracle bracket notation like [DATAM8].[DIMTIME]
        
        Args:
            table_name (str): Table name, potentially including schema
            
        Returns:
            tuple[Optional[str], str]: (schema_name, table_name)
        """
        # Remove brackets if present
        clean_table_name = table_name.replace('[', '').replace(']', '')
        
        if '.' in clean_table_name:
            parts = clean_table_name.split('.')
            if len(parts) == 2:
                return parts[0].upper(), parts[1].upper()
            elif len(parts) > 2:
                # Handle cases like database.schema.table
                return '.'.join(parts[:-1]).upper(), parts[-1].upper()
        
        return None, clean_table_name.upper()