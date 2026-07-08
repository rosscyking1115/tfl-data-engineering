-- Phase 5: least-privilege role for the MCP server.
-- The server connects as this role, so it CANNOT write even if a tool were buggy —
-- the guardrail lives in Snowflake, not in Python. Run once as ACCOUNTADMIN.
-- Usage: python mcp/run_sql.py mcp/setup_readonly_role.sql

use role ACCOUNTADMIN;

create role if not exists TFL_GOLD_READONLY;

-- run + read gold, nothing else
grant usage on warehouse TFL_WH to role TFL_GOLD_READONLY;
grant usage on database TFL to role TFL_GOLD_READONLY;
grant usage on schema TFL.GOLD to role TFL_GOLD_READONLY;
grant select on all tables in schema TFL.GOLD to role TFL_GOLD_READONLY;
grant select on future tables in schema TFL.GOLD to role TFL_GOLD_READONLY;
grant select on all views in schema TFL.GOLD to role TFL_GOLD_READONLY;
grant select on future views in schema TFL.GOLD to role TFL_GOLD_READONLY;

-- assign to the human user so the MCP server can assume it
grant role TFL_GOLD_READONLY to user ROSSCYKING;

-- deliberately NOT granted: any SILVER/RAW access, any DDL/DML, any other warehouse.
