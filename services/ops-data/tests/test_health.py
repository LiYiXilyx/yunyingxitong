import asyncio
import importlib.util
import os
import pytest

def client():
    assert importlib.util.find_spec('ops_data.app'), 'T02 application factory missing'
    from ops_data.app import create_app
    import httpx
    class Client:
        def request(self,method,url,**kwargs):
            async def run():
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()),base_url='http://test') as c:
                    return await c.request(method,url,**kwargs)
            return asyncio.run(run())
        def get(self,url): return self.request('GET',url)
        def post(self,url,**kwargs): return self.request('POST',url,**kwargs)
    return Client()

def test_live_and_no_business_routes(monkeypatch):
    monkeypatch.delenv('OPS_DATABASE_URL',raising=False)
    c=client()
    assert c.get('/health/live').json()=={'status':'live'}
    assert c.post('/v1/review-requests',json={}).status_code==404
    assert c.get('/health/ready').status_code==503

def test_ready_unreachable_does_not_leak(monkeypatch):
    monkeypatch.setenv('OPS_DATABASE_URL','postgresql://secret-user:secret-password@127.0.0.1:1/secret-db?connect_timeout=1')
    r=client().get('/health/ready')
    assert r.status_code==503
    assert r.json()=={'status':'not_ready'}

@pytest.mark.skipif(not os.getenv('OPS_TEST_DATABASE_URL'),reason='real PostgreSQL integration requires OPS_TEST_DATABASE_URL')
def test_ready_real_database(monkeypatch):
    monkeypatch.setenv('OPS_DATABASE_URL',os.environ['OPS_TEST_DATABASE_URL'])
    r=client().get('/health/ready')
    assert r.status_code==200
    assert r.json()=={'status':'ready'}
