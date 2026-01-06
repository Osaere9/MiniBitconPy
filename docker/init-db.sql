-- Create databases for each node
CREATE DATABASE minichain_node1;
CREATE DATABASE minichain_node2;
CREATE DATABASE minichain_node3;

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE minichain_node1 TO postgres;
GRANT ALL PRIVILEGES ON DATABASE minichain_node2 TO postgres;
GRANT ALL PRIVILEGES ON DATABASE minichain_node3 TO postgres;
