"""Create only the two fixed disposable local databases, without psql."""
import argparse
import psycopg
from psycopg import sql

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', type=int, default=55432)
args = parser.parse_args()
if not 1024 <= args.port <= 65535:
    parser.error('Port must be unprivileged and valid')
with psycopg.connect(host='127.0.0.1',port=args.port,user='digest',dbname='postgres',autocommit=True) as db:
    for name in ('digest','digest_pipeline_test'):
        if not db.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,)).fetchone():
            db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
            print('Created',name)
