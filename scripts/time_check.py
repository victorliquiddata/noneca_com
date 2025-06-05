from datetime import datetime, timezone

now_local = datetime.now()
now_utc = datetime.utcnow()

print("Local time:", now_local)
print("UTC time:  ", now_utc)
