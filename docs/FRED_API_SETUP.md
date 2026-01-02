# Quick Setup Guide: FRED API Key

## Why You Need This

The FRED (Federal Reserve Economic Data) API provides real-time economic data:
- **10-Year Treasury Rate** - Used as the risk-free rate in WACC calculations
- **Inflation Data** - CPI year-over-year changes
- **GDP Growth** - Real GDP growth rates

Without a valid API key, the system uses a fallback rate of 4.0%, which may not reflect current market conditions.

---

## Option 1: Interactive Setup (Recommended)

Run the setup helper script:

```bash
uv run python setup_fred_key.py
```

This will:
1. Check your current configuration
2. Guide you through getting an API key
3. Automatically update `config/secrets.env`
4. Create a backup of your old configuration

---

## Option 2: Manual Setup

### Step 1: Get Your Free API Key

1. Go to: https://fred.stlouisfed.org/docs/api/api_key.html
2. Click "Request API Key"
3. Fill out the form:
   - Email address
   - First and last name
   - Organization (can be "Personal")
   - Agree to terms
4. Submit - you'll receive your API key immediately

**Key Format**: Exactly 32 lowercase alphanumeric characters
Example: `1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p`

### Step 2: Update secrets.env

1. Open `config/secrets.env` in your editor
2. Find this line:
   ```bash
   FRED_API_KEY=your_fred_api_key_here
   ```
3. Replace `your_fred_api_key_here` with your actual key:
   ```bash
   FRED_API_KEY=1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p
   ```
4. Save the file

### Step 3: Verify It Works

```bash
uv run python test_integrations.py
```

You should see:
```
✅ FRED_API_KEY found: 1a2b3c4d...5o6p
✅ FRED API Connection: Working
   Source: FRED
   Risk-Free Rate (10Y Treasury): 0.0416 (4.16%)
```

---

## Current Status

Your current FRED API configuration:

```bash
# Check status
cat config/secrets.env | grep FRED_API_KEY
```

**Current value**: `FRED_API_KEY=your_fred_api_key_here`

This is a placeholder - the system will use fallback rates until you set a real API key.

---

## API Limits (Free Tier)

- **Rate Limit**: 120 requests per minute
- **Daily Limit**: None
- **Cost**: Free forever
- **Perfect for**: Personal use, research, small applications

The DCF system caches FRED data for 24 hours, so you'll typically only make 1-3 API calls per day.

---

## Troubleshooting

### Error: "Bad Request. The value for variable api_key is not a 32 character..."

**Problem**: Your API key is not exactly 32 characters or contains invalid characters.

**Solution**: 
1. Double-check you copied the entire key
2. Make sure there are no spaces before/after the key
3. FRED keys are lowercase only: a-z and 0-9

### Error: "FRED_API_KEY not found in environment variables"

**Problem**: The secrets.env file wasn't loaded.

**Solution**:
1. Make sure `config/secrets.env` exists (not `.env.example`)
2. Verify the file has the line `FRED_API_KEY=...`
3. Restart your terminal/session

### API Key Works But Getting Old Data

**Problem**: Data is cached.

**Solution**: Wait 24 hours or delete the cache:
```bash
rm -rf data/cache/treasury_10y_yield.json
```

---

## Security Notes

⚠️ **Never commit your API key to version control!**

- The `.gitignore` file already excludes `config/secrets.env`
- Never share your key publicly
- If you accidentally expose it, regenerate a new one at the FRED website

---

## Alternative: Use Environment Variables

Instead of `config/secrets.env`, you can set the key as a system environment variable:

### macOS/Linux:
```bash
export FRED_API_KEY="your_key_here"
```

Add to `~/.zshrc` or `~/.bashrc` for persistence.

### Windows (PowerShell):
```powershell
$env:FRED_API_KEY="your_key_here"
```

Add to PowerShell profile for persistence.

---

## Need Help?

Run the interactive setup:
```bash
uv run python setup_fred_key.py
```

Or check the integration test:
```bash
uv run python test_integrations.py
```

Both scripts will show you exactly what's wrong and how to fix it.
