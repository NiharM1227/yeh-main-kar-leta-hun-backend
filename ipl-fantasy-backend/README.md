# IPL Fantasy League 2026

A live fantasy cricket league app with AI-powered scorecard reading.

## Setup on Railway

### Environment Variables (set in Railway dashboard)
- `ANTHROPIC_API_KEY` — your Anthropic API key
- `ADMIN_KEY` — a password you choose for the admin upload panel (e.g. `ipl2026admin`)

## Usage

- **Main app**: `your-app.railway.app/`
- **Admin panel**: `your-app.railway.app/admin`

## Adding a new match

1. Go to `/admin`
2. Enter your admin key
3. Type the match name (e.g. `CSK vs MI`)
4. Upload the batting scorecard screenshot
5. Upload the bowling scorecard screenshot with the same match name
6. Points update immediately
