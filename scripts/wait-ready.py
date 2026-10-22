#!/usr/bin/env python3
import argparse
import time
import urllib.error
import urllib.request
p=argparse.ArgumentParser();p.add_argument('url');p.add_argument('--codes',default='200');p.add_argument('--timeout',type=int,default=45);a=p.parse_args()
codes={int(c) for c in a.codes.split(',')};deadline=time.monotonic()+a.timeout
while time.monotonic()<deadline:
    try:
        with urllib.request.urlopen(a.url,timeout=3) as r:
            if r.status in codes: break
    except urllib.error.HTTPError as exc:
        if exc.code in codes: break
    except (urllib.error.URLError,TimeoutError,ConnectionError): pass
    time.sleep(1)
else: raise SystemExit('Readiness timeout; inspect local service logs')
print('Ready: '+a.url)
