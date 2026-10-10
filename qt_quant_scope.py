"""Pure helpers for QUANT scope and temporal cropping; scientific QUANT core unchanged."""
import pandas as pd
import re

def normalize_id(value):
    s=str(value).strip()
    try:
        f=float(s)
        return str(int(f)) if f.is_integer() else str(f)
    except (ValueError,TypeError):return s

def resolve_start(value,year=None,kind='auto'):
    if pd.isna(value) or str(value).strip()=='':raise ValueError('Missing start date/DOY')
    s=str(value).strip()
    if kind=='doy' or (kind=='auto' and re.fullmatch(r'\d{1,3}(?:\.0+)?',s)):
        if year is None:raise ValueError('DOY requires a reference year')
        doy=int(float(s));first=pd.Timestamp(year=int(year),month=1,day=1)
        days=366 if first.is_leap_year else 365
        if not 1<=doy<=days:raise ValueError(f'DOY {doy} invalid for {year}')
        return first+pd.Timedelta(days=doy-1)
    try:
        dt=pd.to_datetime(value,errors='raise',dayfirst=False)
        if pd.isna(dt):raise ValueError('Invalid start date')
        return pd.Timestamp(dt).normalize()
    except (ValueError,TypeError,OverflowError) as exc:raise ValueError(f'Invalid start date: {value}') from exc

def filter_daily(df,start_date):
    if start_date is None:return df.copy()
    return df[pd.to_datetime(df['date'])>=pd.Timestamp(start_date)].copy()
