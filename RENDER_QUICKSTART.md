# Quick Start: Deploy to Render

## 🚀 Fast Deployment (5 minutes)

### Step 1: Push to GitHub
```bash
git add .
git commit -m "Add Render deployment config"
git push
```

### Step 2: Deploy on Render

1. Go to https://render.com and sign up (free)
2. Click **"New +"** → **"Blueprint"**
3. Connect your GitHub account
4. Select your repository
5. Render will auto-detect `render.yaml`
6. Click **"Apply"**

### Step 3: Wait & Test

- First deployment: **5-10 minutes** (Playwright install)
- You'll get a URL like: `https://scholar-scraper.onrender.com`
- Test it by scraping a profile!

## ✅ That's it!

Your app is now live and shareable!

## 📝 Notes

- **Free tier**: 750 hours/month
- **Cold starts**: First request after 15 min inactivity takes 30-60 seconds
- **Auto-deploy**: Pushes to GitHub automatically redeploy

## 🆘 Need Help?

See `DEPLOYMENT.md` for detailed instructions and troubleshooting.

