# Deployment Guide for Render

This guide will help you deploy the Google Scholar Scraper to Render's free tier.

## Prerequisites

1. A GitHub account
2. Your code pushed to a GitHub repository
3. A Render account (sign up at https://render.com - it's free!)

## Step-by-Step Deployment

### 1. Push Your Code to GitHub

If you haven't already, push your code to GitHub:

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin <your-github-repo-url>
git push -u origin main
```

### 2. Create Render Account

1. Go to https://render.com
2. Sign up with your GitHub account (recommended) or email
3. Verify your email if required

### 3. Deploy to Render

#### Option A: Using render.yaml (Recommended)

1. Go to your Render dashboard
2. Click "New +" → "Blueprint"
3. Connect your GitHub repository
4. Render will automatically detect `render.yaml` and use those settings
5. Click "Apply" to deploy

#### Option B: Manual Configuration

1. Go to your Render dashboard
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Select your repository
5. Configure the service:
   - **Name**: `scholar-scraper` (or any name you prefer)
   - **Region**: Choose the closest region to your users
   - **Branch**: `main` (or your default branch)
   - **Root Directory**: (leave empty if your files are in the root)
   - **Runtime**: `Python 3`
   - **Build Command**: 
     ```
     pip install -r requirements.txt && playwright install chromium && playwright install-deps chromium
     ```
   - **Start Command**: 
     ```
     uvicorn server:app --host 0.0.0.0 --port $PORT
     ```
   - **Plan**: `Free`
6. Click "Create Web Service"

### 4. Wait for Deployment

- First deployment takes **5-10 minutes** (Playwright installation is slow)
- You'll see build logs in real-time
- Once deployed, you'll get a URL like: `https://scholar-scraper.onrender.com`

### 5. Test Your Deployment

1. Visit your Render URL
2. Try scraping a Google Scholar profile
3. Check that the web interface loads correctly

## Important Notes

### Free Tier Limitations

- **750 hours/month** - Usually enough for moderate usage
- **Spins down after 15 minutes** of inactivity
- **Cold starts**: First request after spin-down takes 30-60 seconds
- **No persistent storage** - Files are ephemeral (artifacts will be lost on restart)

### Environment Variables

No environment variables are required for basic deployment. The app will work out of the box.

### Troubleshooting

#### Build Fails

- Check build logs in Render dashboard
- Ensure `requirements.txt` is correct
- Verify Python version compatibility (3.11.0 is specified in render.yaml)

#### Playwright Installation Issues

- The build command includes `playwright install-deps chromium` which installs system dependencies
- If it fails, check Render's build logs for specific errors

#### App Crashes

- Check logs in Render dashboard
- Verify the start command is correct
- Ensure all dependencies are in `requirements.txt`

#### Slow First Request

- This is normal on free tier (cold start)
- After 15 minutes of inactivity, the service spins down
- First request wakes it up (takes 30-60 seconds)
- Subsequent requests are fast

### Updating Your Deployment

1. Push changes to your GitHub repository
2. Render automatically detects changes and redeploys
3. Or manually trigger a deploy from Render dashboard

### Monitoring

- View logs in Render dashboard
- Check service health status
- Monitor usage hours (free tier: 750/month)

## Custom Domain (Optional)

If you want a custom domain:

1. Go to your service settings in Render
2. Click "Custom Domains"
3. Add your domain
4. Follow DNS configuration instructions

## Support

- Render Documentation: https://render.com/docs
- Render Community: https://community.render.com
- Check Render status: https://status.render.com

## Next Steps

After deployment:

1. Share your Render URL with others
2. Test the scraper with different profiles
3. Monitor usage to stay within free tier limits
4. Consider upgrading to paid plan if you need:
   - No spin-downs
   - Persistent storage
   - More resources

