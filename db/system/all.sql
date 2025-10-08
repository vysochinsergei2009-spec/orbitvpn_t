SELECT 
    table_name AS "Table",
    column_name AS "Column",
    data_type AS "Type"
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;