# Restoration Guide: From Backup to Full ML System

## Problem

When you restore from `money_machine_backup.tar.gz`:
- ❌ Old `requirements.txt` hangs (TensorFlow/PyTorch = 4.5GB)
- ❌ ML integration files missing (created after backup)
- ❌ Split requirements structure needs setup

## Solution: Step-by-Step Restoration

---

### Step 1: Extract Backup

```bash
cd /mnt/c/Users/catty/Desktop
tar -xzf money_machine_backup.tar.gz
cd money_machine
```

**What you have:**
- ✅ All source code
- ✅ Old requirements.txt (bloated)
- ✅ New requirements-*.txt files (if backup was after refactor)
- ❌ ML integration files (created later)

---

### Step 2: Fix Dependencies (Don't Use Old requirements.txt!)

**DO THIS:**
```bash
# Create fresh virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install ONLY core packages (5 min, no hanging)
pip install -r requirements-core.txt
```

**DON'T DO THIS:**
```bash
pip install -r requirements.txt  # ❌ This will hang for hours!
```

**If requirements-core.txt is missing:**
```bash
# Use the incremental installer instead
chmod +x install_packages.sh
./install_packages.sh
```

---

### Step 3: Regenerate ML Files

**Option A: Ask Claude to Recreate**

In Claude Code, say:
> "Recreate all the ML integration files from our earlier session:
> - src/ai/opportunity_logger.py
> - src/live/flash_arb_ml_runner.py
> - scripts/train_slippage_model.py
> - scripts/init_ml_schema.sql
> - scripts/setup_ml.sh
> - docs/ML_INTEGRATION_GUIDE.md
> - ML_QUICKSTART.md"

Claude will regenerate all files with the same content.

**Option B: Save Files Before Restoring (Preventative)**

Before you restore from backup, save ML files:
```bash
# From current working directory (BEFORE restoring)
mkdir /tmp/ml_backup
cp -r src/ai/opportunity_logger.py /tmp/ml_backup/
cp -r src/ai/slippage_predictor.py /tmp/ml_backup/
cp -r src/live/flash_arb_ml_runner.py /tmp/ml_backup/
cp -r scripts/train_slippage_model.py /tmp/ml_backup/
cp -r scripts/init_ml_schema.sql /tmp/ml_backup/
cp -r scripts/setup_ml.sh /tmp/ml_backup/
cp -r docs/ML_INTEGRATION_GUIDE.md /tmp/ml_backup/
cp ML_QUICKSTART.md /tmp/ml_backup/

# After restoring from backup
cp /tmp/ml_backup/* money_machine/[appropriate-directories]/
```

**Option C: Commit to Git First**

```bash
# BEFORE restoring backup
git add -A
git commit -m "ML integration complete"
git push

# AFTER restoring backup
git pull  # Or git checkout specific files
```

---

### Step 4: Install ML Dependencies

```bash
# Once core packages are installed
pip install -r requirements-ml.txt  # 5 min, no hanging
```

---

### Step 5: Setup ML System

```bash
chmod +x scripts/setup_ml.sh
./scripts/setup_ml.sh
```

---

## Quick Reference: File Checklist

After restoration, verify these files exist:

### Core Requirements
- [ ] `requirements-core.txt` (500MB, 5 min install)
- [ ] `requirements-ml.txt` (350MB, 5 min install)
- [ ] `requirements-dev.txt` (optional)
- [ ] `requirements-analysis.txt` (optional)

### ML Integration Files
- [ ] `src/ai/opportunity_logger.py`
- [ ] `src/ai/slippage_predictor.py`
- [ ] `src/live/flash_arb_ml_runner.py`
- [ ] `scripts/train_slippage_model.py`
- [ ] `scripts/init_ml_schema.sql`
- [ ] `scripts/setup_ml.sh`
- [ ] `docs/ML_INTEGRATION_GUIDE.md`
- [ ] `ML_QUICKSTART.md`

### Directories
- [ ] `models/` (created by setup_ml.sh)
- [ ] `src/ai/`
- [ ] `src/live/`
- [ ] `docs/`

---

## Common Issues

### "requirements.txt hanging"
**Solution**: Don't use it! Use `requirements-core.txt` instead.

### "ML files missing after restore"
**Solution**: They were created after backup. Ask Claude to regenerate or use git.

### "Can't install packages at all"
**Solution**: Use incremental installer:
```bash
./install_packages.sh
```

### "Database schema missing"
**Solution**:
```bash
docker exec -it trading_timescaledb psql -U trading_user -d trading_db -f /tmp/init_ml_schema.sql
```

---

## The Smart Way: Version Control

**Best practice going forward:**

```bash
# After every major change
git add -A
git commit -m "Description of changes"
git push

# Create tagged releases
git tag -a v1.0-ml-integration -m "ML integration complete"
git push origin v1.0-ml-integration
```

Then restoration is simple:
```bash
git clone <your-repo>
cd money_machine
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-core.txt
pip install -r requirements-ml.txt
./scripts/setup_ml.sh
```

---

## Summary: Restoration Steps

1. ✅ Extract backup
2. ✅ Create fresh `.venv`
3. ✅ Install `requirements-core.txt` (NOT requirements.txt!)
4. ✅ Regenerate ML files (ask Claude or restore from git)
5. ✅ Install `requirements-ml.txt`
6. ✅ Run `./scripts/setup_ml.sh`
7. ✅ Verify with checklist above

**Total time**: 15-20 minutes (vs hours of hanging!)

---

## Files to Keep Safe

Store these separately from backups:
- `.env` (credentials)
- `models/*.json` (trained ML models)
- Database dumps (if you want to preserve training data)

**Don't rely on tar.gz backups** - use git instead!
