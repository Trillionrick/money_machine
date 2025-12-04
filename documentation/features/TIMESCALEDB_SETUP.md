# TimescaleDB Setup Guide for OANDA Integration

This guide provides multiple methods to set up TimescaleDB for your OANDA forex trading data.

---

## Option 1: Docker Desktop (Recommended for Windows/WSL2)

### Step 1: Fix Docker Credentials (if needed)

If you're getting credential errors in WSL2:

1. **Open PowerShell as Administrator** and run:
   ```powershell
   wsl --update
   ```

2. **In WSL2**, create/edit `~/.docker/config.json`:
   ```bash
   mkdir -p ~/.docker
   cat > ~/.docker/config.json << 'EOF'
   {
     "credsStore": ""
   }
   EOF
   ```

3. **Restart Docker Desktop**

### Step 2: Start TimescaleDB

```bash
# From project root
cd /mnt/c/Users/catty/Desktop/money_machine

# Pull the image
docker pull timescale/timescaledb:latest-pg16

# Start services
docker compose up -d timescaledb

# Check logs
docker logs trading_timescaledb

# Wait 30 seconds for initialization
sleep 30
```

### Step 3: Verify Setup

```bash
# Install Python dependencies
pip install asyncpg

# Run verification script
python scripts/verify_db_setup.py
```

### Step 4: Fetch Initial Data

```bash
# Make sure .env has OANDA credentials
python scripts/fetch_initial_data.py
```

---

## Option 2: Manual Docker Run (No Docker Compose)

If Docker Compose isn't working:

```bash
# Create data directory
mkdir -p ./data/timescaledb

# Run TimescaleDB container
docker run -d \
  --name trading_timescaledb \
  -p 5433:5432 \
  -e POSTGRES_USER=trading_user \
  -e POSTGRES_PASSWORD=trading_pass_change_in_production \
  -e POSTGRES_DB=trading_db \
  -v "$(pwd)/data/timescaledb:/var/lib/postgresql/data" \
  timescale/timescaledb:latest-pg16

# Wait for startup
sleep 30

# Initialize schema
docker exec -i trading_timescaledb psql -U trading_user -d trading_db < scripts/init_oanda_schema.sql

# Verify
python scripts/verify_db_setup.py
```

---

## Option 3: Native PostgreSQL + TimescaleDB Extension

If you prefer native installation:

### Ubuntu/Debian WSL2

```bash
# Add TimescaleDB repository
sudo sh -c "echo 'deb https://packagecloud.io/timescale/timescaledb/ubuntu/ $(lsb_release -c -s) main' > /etc/apt/sources.list.d/timescaledb.list"
wget --quiet -O - https://packagecloud.io/timescale/timescaledb/gpgkey | sudo apt-key add -

# Update and install
sudo apt update
sudo apt install -y timescaledb-2-postgresql-16 postgresql-client-16

# Configure
sudo timescaledb-tune --quiet --yes

# Start PostgreSQL
sudo service postgresql start

# Create database and user
sudo -u postgres psql << EOF
CREATE USER trading_user WITH PASSWORD 'trading_pass_change_in_production';
CREATE DATABASE trading_db OWNER trading_user;
\c trading_db
CREATE EXTENSION timescaledb;
\q
EOF

# Initialize schema
psql -h localhost -U trading_user -d trading_db < scripts/init_oanda_schema.sql

# Verify
python scripts/verify_db_setup.py
```

---

## Option 4: Use Existing PostgreSQL

If you already have PostgreSQL running (like in money_graphic):

### Step 1: Add TimescaleDB Extension

```bash
# Connect to your existing PostgreSQL
docker exec -it money_graphic-postgres-1 psql -U graph-node

# In psql:
CREATE DATABASE trading_db;
CREATE USER trading_user WITH PASSWORD 'trading_pass_change_in_production';
GRANT ALL PRIVILEGES ON DATABASE trading_db TO trading_user;
\c trading_db
CREATE EXTENSION timescaledb;
\q
```

### Step 2: Update Connection Settings

Edit `scripts/verify_db_setup.py` and `scripts/fetch_initial_data.py`:

```python
# Change port from 5433 to 5432
config = {
    "host": "localhost",
    "port": 5432,  # Changed from 5433
    "user": "trading_user",
    "password": "trading_pass_change_in_production",
    "database": "trading_db",
}
```

### Step 3: Initialize Schema

```bash
docker exec -i money_graphic-postgres-1 psql -U trading_user -d trading_db < scripts/init_oanda_schema.sql
```

### Step 4: Verify

```bash
python scripts/verify_db_setup.py
```

---

## Troubleshooting

### 1. Docker Credential Error

**Error**: `error getting credentials - err: exec: "docker-credential-desktop.exe"`

**Solution**:
```bash
# Edit Docker config
nano ~/.docker/config.json

# Change to:
{
  "credsStore": ""
}

# Restart Docker Desktop
```

### 2. Port Already in Use

**Error**: `port is already allocated`

**Solution**:
```bash
# Check what's using port 5433
netstat -ano | grep 5433

# Either:
# A) Stop the conflicting service
# B) Change port in docker-compose.yml to 5434 or 5435
```

### 3. Permission Denied on Data Directory

**Error**: `permission denied` in Docker logs

**Solution**:
```bash
# Fix permissions
sudo chown -R $(id -u):$(id -g) ./data/timescaledb

# Or remove and let Docker recreate
rm -rf ./data/timescaledb
docker compose down
docker compose up -d timescaledb
```

### 4. Schema Not Initialized

**Error**: `relation "oanda_candles" does not exist`

**Solution**:
```bash
# Manually run schema
docker exec -i trading_timescaledb psql -U trading_user -d trading_db < scripts/init_oanda_schema.sql

# Or connect and paste SQL
docker exec -it trading_timescaledb psql -U trading_user -d trading_db
# Then paste contents of scripts/init_oanda_schema.sql
```

### 5. Can't Connect from Python

**Error**: `Connection refused`

**Solution**:
```bash
# Check container is running
docker ps | grep timescale

# Check PostgreSQL is accepting connections
docker exec trading_timescaledb pg_isready -U trading_user

# Try connecting with psql first
psql -h localhost -p 5433 -U trading_user -d trading_db
# Password: trading_pass_change_in_production
```

---

## Verification Checklist

After setup, verify everything works:

- [ ] Container is running: `docker ps | grep timescale`
- [ ] Can connect with psql: `psql -h localhost -p 5433 -U trading_user -d trading_db`
- [ ] Verification script passes: `python scripts/verify_db_setup.py`
- [ ] All tables exist: Run `\dt` in psql
- [ ] TimescaleDB extension enabled: Run `\dx` in psql
- [ ] Can fetch data: `python scripts/fetch_initial_data.py`

---

## Quick Commands Reference

```bash
# Start database
docker compose up -d timescaledb

# Stop database
docker compose down

# View logs
docker logs trading_timescaledb -f

# Connect with psql
psql -h localhost -p 5433 -U trading_user -d trading_db

# Backup database
docker exec trading_timescaledb pg_dump -U trading_user trading_db > backup.sql

# Restore database
cat backup.sql | docker exec -i trading_timescaledb psql -U trading_user -d trading_db

# Check database size
docker exec trading_timescaledb psql -U trading_user -d trading_db -c "SELECT pg_size_pretty(pg_database_size('trading_db'));"

# Remove all data and start fresh
docker compose down
rm -rf ./data/timescaledb
docker compose up -d timescaledb
sleep 30
python scripts/verify_db_setup.py
```

---

## Next Steps

Once TimescaleDB is running:

1. ✅ Verify setup: `python scripts/verify_db_setup.py`
2. ✅ Fetch historical data: `python scripts/fetch_initial_data.py`
3. ✅ Start streaming prices: Create `examples/stream_forex_prices.py`
4. ✅ Query data: `psql -h localhost -p 5433 -U trading_user -d trading_db`

---

## Production Recommendations

Before going to production:

1. **Change Default Password**
   ```bash
   # Update docker-compose.yml
   POSTGRES_PASSWORD: your_secure_password_here
   ```

2. **Enable SSL/TLS**
   ```yaml
   # In docker-compose.yml
   command:
     - "postgres"
     - "-c"
     - "ssl=on"
     - "-c"
     - "ssl_cert_file=/etc/ssl/certs/server.crt"
     - "-c"
     - "ssl_key_file=/etc/ssl/private/server.key"
   ```

3. **Set Up Backups**
   ```bash
   # Add to crontab
   0 2 * * * docker exec trading_timescaledb pg_dump -U trading_user trading_db | gzip > /backups/trading_db_$(date +\%Y\%m\%d).sql.gz
   ```

4. **Monitor Disk Usage**
   ```sql
   -- Query to monitor table sizes
   SELECT
       hypertable_name,
       pg_size_pretty(total_bytes) as total_size,
       pg_size_pretty(index_bytes) as index_size,
       pg_size_pretty(toast_bytes) as toast_size
   FROM hypertable_approximate_detailed_size('oanda_candles');
   ```

5. **Configure Connection Pooling** (for high-traffic applications)
   - Use PgBouncer or similar
   - Limit max connections in PostgreSQL config

---

## Support

If you're still having issues:

1. Check Docker Desktop is running
2. Verify WSL2 integration in Docker Desktop settings
3. Try the "Manual Docker Run" option above
4. Check firewall isn't blocking port 5433
5. Review container logs: `docker logs trading_timescaledb`

For OANDA API issues, see `documentation/oanda_integration_guide.md`
