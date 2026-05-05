import psycopg2
conn = psycopg2.connect(
    host='atlantic-highlands-db.c4xoyiqaey7u.us-east-1.rds.amazonaws.com',
    user='ahAdmin', password='AH-Docs-2026!',
    dbname='atlantic_highlands', connect_timeout=10,
)
cur = conn.cursor()
cur.execute('SELECT count(*) FROM parcels')
print(f'Parcels in DB: {cur.fetchone()[0]}')

cur.execute("""
SELECT property_class, count(*), sum(total_assessment)::bigint
FROM parcels GROUP BY property_class ORDER BY 2 DESC
""")
print('\nBy property class:')
for r in cur.fetchall():
    cls = r[0] or '(null)'
    print(f'  {cls:6}  count={r[1]:>5}  total_assessment={(r[2] or 0):>15,}')

cur.execute("""
SELECT coalesce(owner_name,'(null)'), count(*), sum(total_assessment)::bigint
FROM parcels WHERE total_assessment > 0
GROUP BY owner_name ORDER BY 3 DESC LIMIT 8
""")
print('\nTop 8 owners by total assessment:')
for r in cur.fetchall():
    print(f'  {r[0][:50]:50}  parcels={r[1]:>3}  total={r[2]:>12,}')

cur.close()
conn.close()
