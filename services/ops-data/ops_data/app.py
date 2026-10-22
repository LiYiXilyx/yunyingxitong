"""T02 service skeleton. Business routes are deliberately not registered."""
import os
import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse

def create_app():
    app=FastAPI(title='Ops data health',version='0.1.0',docs_url=None,redoc_url=None,openapi_url=None)

    @app.get('/health/live')
    def live():
        return {'status':'live'}

    @app.get('/health/ready')
    def ready():
        database_url=os.getenv('OPS_DATABASE_URL')
        if not database_url: return JSONResponse({'status':'not_ready'},status_code=503)
        try:
            with psycopg.connect(database_url,connect_timeout=3,options='-c statement_timeout=3000') as connection:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT 1')
                    if cursor.fetchone() != (1,): raise RuntimeError('probe failed')
        except Exception:
            # Never expose/log DSNs, server errors, usernames, or credentials.
            return JSONResponse({'status':'not_ready'},status_code=503)
        return {'status':'ready'}

    return app
