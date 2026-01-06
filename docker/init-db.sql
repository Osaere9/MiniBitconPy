-- Create databases for each node
CREATE DATABASE minibitcoinpy_node1;
CREATE DATABASE minibitcoinpy_node2;
CREATE DATABASE minibitcoinpy_node3;

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE minibitcoinpy_node1 TO postgres;
GRANT ALL PRIVILEGES ON DATABASE minibitcoinpy_node2 TO postgres;
GRANT ALL PRIVILEGES ON DATABASE minibitcoinpy_node3 TO postgres;
