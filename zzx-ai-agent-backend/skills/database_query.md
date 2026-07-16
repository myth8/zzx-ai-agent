---
name: database_query
description: SQL查询编写和数据库操作指南
---

# Database Query Skill

This skill helps you write SQL queries against business databases.

## Capabilities

- Write SELECT queries with JOINs, WHERE clauses, GROUP BY, and HAVING
- Create INSERT, UPDATE, DELETE statements
- Understand database schema and relationships
- Optimize query performance with indexes and EXPLAIN plans

## Example Queries

\\sql
-- Get top 10 customers by revenue
SELECT c.name, SUM(o.total) as revenue
FROM customers c
JOIN orders o ON c.id = o.customer_id
WHERE o.created_at >= '2024-01-01'
GROUP BY c.name
ORDER BY revenue DESC
LIMIT 10;
\
## Best Practices

1. Always use parameterized queries to prevent SQL injection
2. Add LIMIT clauses to prevent large result sets
3. Use EXPLAIN to analyze query performance
4. Prefer JOINs over subqueries when possible
