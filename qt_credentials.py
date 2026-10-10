"""Parsing of local CDSE credentials; does not store or print secrets."""

def parse_credentials(text: str) -> tuple[str,str]:
    """Accept CLIENT_ID/CLIENT_SECRET or CDSE_CLIENT_ID/CDSE_CLIENT_SECRET."""
    values={}
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('#'):continue
        if line.startswith('export '):line=line[7:].strip()
        if '=' not in line:continue
        key,value=line.split('=',1)
        key=key.strip().upper()
        if key in {'CLIENT_ID','CLIENT_SECRET','CDSE_CLIENT_ID','CDSE_CLIENT_SECRET'}:
            value=value.strip()
            if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):
                value=value[1:-1]
            values[key]=value
    cid=values.get('CDSE_CLIENT_ID') or values.get('CLIENT_ID')
    secret=values.get('CDSE_CLIENT_SECRET') or values.get('CLIENT_SECRET')
    if not cid or not secret:raise ValueError('Missing CLIENT_ID or CLIENT_SECRET in the selected file.')
    return cid,secret
