{# Portability seam (rigor-pass C3): the same models run on Snowflake (the documented
   build warehouse) and DuckDB (the durable, warehouse-free target). Anything the two
   engines spell differently lives here, so model SQL stays engine-agnostic. #}

{% macro collapse_ws(expr) -%}
    {%- if target.type == 'duckdb' -%}
        regexp_replace(trim({{ expr }}), '\s+', ' ', 'g')
    {%- else -%}
        regexp_replace(trim({{ expr }}), '\\s+', ' ')
    {%- endif -%}
{%- endmacro %}

{% macro date_key_int(expr) -%}
    {%- if target.type == 'duckdb' -%}
        cast(strftime({{ expr }}, '%Y%m%d') as integer)
    {%- else -%}
        to_number(to_char({{ expr }}, 'YYYYMMDD'))
    {%- endif -%}
{%- endmacro %}

{% macro iso_dow(expr) -%}
    {%- if target.type == 'duckdb' -%}
        isodow({{ expr }})
    {%- else -%}
        dayofweekiso({{ expr }})
    {%- endif -%}
{%- endmacro %}
