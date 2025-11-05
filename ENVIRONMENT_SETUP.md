# Environment Setup Guide

## Setting Up Your API Keys

George AI uses environment variables to securely store API keys and configuration.

### Step 1: Create Your `.env` File

1. Copy the example file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your actual API key:
   ```
   GEMINI_API_KEY=your-actual-api-key-here
   ```

### Step 2: Get Your Gemini API Key

1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the key and paste it into your `.env` file

### Step 3: Security Best Practices

✅ **DO:**
- Keep your `.env` file in the `.gitignore` (already configured)
- Never commit API keys to version control
- Use different API keys for development and production
- Rotate your keys periodically

❌ **DON'T:**
- Share your `.env` file
- Commit your API keys to GitHub
- Use production keys in development
- Hardcode API keys in source code

## Configuration Options

Your `.env` file can include:

```bash
# Required: Google Gemini API Key
GEMINI_API_KEY=your-key-here

# Optional: Flask Configuration
FLASK_SECRET_KEY=your-secret-key-here
FLASK_DEBUG=True
```

## Running the Application

Once your `.env` file is configured, simply run:

```bash
python src/george/ui/app_simple.py
```

The application will automatically load your environment variables from `.env`.

## Troubleshooting

**Error: "API key is required"**
- Make sure your `.env` file exists in the project root
- Check that `GEMINI_API_KEY` is spelled correctly
- Ensure there are no spaces around the `=` sign
- Verify your API key is valid

**Error: "No module named 'dotenv'"**
- Install the required package: `pip install python-dotenv`
