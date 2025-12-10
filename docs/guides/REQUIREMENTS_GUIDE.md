# Requirements Guide

## File Structure

```
requirements-core.txt      # Essential packages (ALWAYS INSTALL)
requirements-dev.txt       # Testing & code quality tools
requirements-ml.txt        # Machine learning packages
requirements-analysis.txt  # Data analysis & visualization
requirements.txt           # OLD FILE - deprecated, use above instead
```

## Installation Scenarios

### Fresh Setup (Minimal - 5 minutes)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-core.txt
```

**Installs**: 500MB
**Use for**: Running the arbitrage system in production

---

### Development Setup (10 minutes)
```bash
pip install -r requirements-core.txt -r requirements-dev.txt
```

**Installs**: 650MB
**Use for**: Contributing code, running tests, type checking

---

### ML-Enhanced Setup (15 minutes)
```bash
pip install -r requirements-core.txt -r requirements-ml.txt
```

**Installs**: 850MB
**Use for**: Slippage prediction, gas forecasting

---

### Full Analytics Setup (20 minutes)
```bash
pip install -r requirements-core.txt \
            -r requirements-dev.txt \
            -r requirements-ml.txt \
            -r requirements-analysis.txt
```

**Installs**: 1.2GB
**Use for**: Data science, backtesting, research

---

### Deep Learning Setup (45+ minutes)
```bash
# Edit requirements-ml.txt: Uncomment torch/tensorflow lines
pip install -r requirements-core.txt -r requirements-ml.txt
```

**Installs**: 5GB+
**Use for**: LSTM gas forecasting, transformer models

---

## Migration from Old requirements.txt

Your old `requirements.txt` had everything mixed together (4.5GB).

**To migrate:**

1. **Backup**: Already done at `money_machine_backup.tar.gz`

2. **Rename old file**:
   ```bash
   mv requirements.txt requirements-old.txt
   ```

3. **Install new structure**:
   ```bash
   pip install -r requirements-core.txt
   ```

4. **Test**: Your system should work identically

5. **Add ML later** when you need it:
   ```bash
   pip install -r requirements-ml.txt
   ```

---

## What Changed

### Before (requirements.txt - 4.5GB)
- ❌ TensorFlow (2.5GB) - Not used
- ❌ PyTorch (2GB) - Not used
- ❌ Many unused ML packages
- ⏱️ 30+ minute install
- 🐌 Slow, confusing

### After (requirements-core.txt - 500MB)
- ✅ Only what you actually use
- ✅ Fast 5-minute install
- ✅ Clear separation of concerns
- ✅ Optional ML packages when needed

---

## Recommended Workflow

**Day 1**: Install core
```bash
pip install -r requirements-core.txt
```

**Week 1**: Add development tools
```bash
pip install -r requirements-dev.txt
```

**Month 1**: After collecting data, add ML
```bash
pip install -r requirements-ml.txt
```

**Month 3**: When you need deep learning
```bash
# Edit requirements-ml.txt to uncomment torch
pip install torch
```

---

## Current Status

Your system is **already running** with packages installed ad-hoc. To clean up:

```bash
# Create fresh venv
rm -rf .venv
python -m venv .venv
source .venv/bin/activate

# Install only what you need
pip install -r requirements-core.txt

# Test
./start_dashboard.sh
```
