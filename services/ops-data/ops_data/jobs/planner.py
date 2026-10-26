"""Frozen half-open UTC query windows; business days follow IANA local dates."""
from datetime import datetime, timedelta, timezone as dt_timezone, time
from zoneinfo import ZoneInfo
from ..ingestion.repository import timestamp


def _utc(value):
    return timestamp(value) if isinstance(value,str) else timestamp(value.isoformat())


def _split(data_type,start,end,zone=None):
    if data_type not in ('orders','refunds','inventory','catalog'): raise ValueError('data_type_invalid')
    limit={'orders':90,'refunds':30}.get(data_type,28)
    windows=[]
    while start<end:
        if zone:
            local=start.astimezone(zone)
            stop=datetime.combine(local.date()+timedelta(days=limit),time.min,zone).astimezone(dt_timezone.utc)
        else: stop=start+timedelta(days=limit)
        stop=min(stop,end); windows.append((start,stop)); start=stop
    return windows


def history_plan(data_type,timezone,now=None,days=28):
    if type(days) is not int or days<1: raise ValueError('days_invalid')
    zone=ZoneInfo(timezone); current=now or datetime.now(dt_timezone.utc)
    if current.tzinfo is None: raise ValueError('timezone_required')
    end_date=current.astimezone(zone).date()
    start=datetime.combine(end_date-timedelta(days=days),time.min,zone).astimezone(dt_timezone.utc)
    end=datetime.combine(end_date,time.min,zone).astimezone(dt_timezone.utc)
    return _split(data_type,start,end,zone)


def incremental_plan(data_type,cursor,frozen_end,*,overlap_seconds=0,timestamp_api_confirmed=False):
    if data_type=='inventory' and timestamp_api_confirmed is not True: raise ValueError('inventory_timestamp_unconfirmed')
    if type(overlap_seconds) is not int or overlap_seconds<0: raise ValueError('overlap_invalid')
    start=_utc(cursor)-timedelta(seconds=overlap_seconds); end=_utc(frozen_end)
    if start>=end: raise ValueError('window_invalid')
    return _split(data_type,start,end)
