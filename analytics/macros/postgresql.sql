{% macro date_key(value) -%}
    cast(to_char({{ value }}, 'YYYYMMDD') as integer)
{%- endmacro %}

{% macro sanitize_json(value) -%}
    replace(
        replace(
            replace(coalesce({{ value }}, '{}'), '-Infinity', 'null'),
            'Infinity', 'null'
        ),
        'NaN', 'null'
    )
{%- endmacro %}

{% macro json_text(value, key) -%}
    (cast({{ sanitize_json(value) }} as jsonb) ->> '{{ key }}')
{%- endmacro %}

{% macro json_number(value, key) -%}
    cast(nullif({{ json_text(value, key) }}, '') as double precision)
{%- endmacro %}

{% macro median(value) -%}
    percentile_cont(0.5) within group (order by {{ value }})
{%- endmacro %}

{% macro date_part_integer(part, value) -%}
    cast(extract({{ part }} from {{ value }}) as integer)
{%- endmacro %}

{% macro date_name(part, value) -%}
    trim(to_char({{ value }}, {% if part == 'month' %}'Month'{% else %}'Day'{% endif %}))
{%- endmacro %}

{% macro normalized_percent(value) -%}
    cast(nullif(regexp_replace({{ value }}, '[^0-9.-]', '', 'g'), '') as double precision) / 100.0
{%- endmacro %}
