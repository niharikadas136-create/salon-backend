# 🚀 QuickSalon Backend - Render Deployment Guide

## 📦 What's Included

This backend package contains:
- `server.py` - FastAPI application
- `requirements.txt` - Python dependencies
- `render.yaml` - Render configuration (auto-deploy)
- `.env.example` - Environment variables template
- This README

## 🎯 Quick Deploy to Render (5 Minutes)

### Step 1: Create MongoDB Database (FREE)

**Option A: MongoDB Atlas (Recommended)**
1. Go to https://www.mongodb.com/cloud/atlas/register
2. Create a **FREE** account
3. Create a **FREE cluster** (M0 Sandbox - 512MB)
4. Click "Connect" → "Connect your application"
5. Copy your connection string:
   ```
   mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
6. Replace `<username>` and `<password>` with your credentials
7. Add your IP to whitelist: Go to "Network Access" → "Add IP Address" → "Allow Access from Anywhere" (0.0.0.0/0)

**Option B: Render PostgreSQL + MongoDB Atlas**
- Render doesn't offer free MongoDB
- Must use MongoDB Atlas free tier

### Step 2: Deploy to Render

#### Method 1: Deploy from GitHub (Recommended)

1. **Create GitHub Repository**
   ```bash
   # On your local machine
   cd backend/
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/yourusername/quicksalon-backend.git
   git push -u origin main
   ```

2. **Deploy on Render**
   - Go to https://render.com/
   - Sign up/Login with GitHub
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Render auto-detects settings from `render.yaml`
   - Click "Create Web Service"

3. **Add Environment Variables**
   In Render dashboard:
   - Go to "Environment" tab
   - Add variable:
     - **Key**: `MONGO_URL`
     - **Value**: Your MongoDB connection string from Step 1
   - Click "Save Changes"
   - Render will automatically redeploy

#### Method 2: Manual Upload (No GitHub)

1. **Prepare ZIP file**
   - You already have `backend.zip` ready
   - Extract and ensure all files are present

2. **Deploy on Render**
   - Go to https://render.com/
   - Sign up/Login
   - Click "New +" → "Web Service"
   - Select "Deploy an existing image from a registry" → **Skip this**
   - Instead, select "Public Git repository"
   - Manually configure:
     - **Name**: quicksalon-backend
     - **Environment**: Python 3
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `uvicorn server:app --host 0.0.0.0 --port $PORT`

3. **Add Environment Variables** (Same as Method 1 Step 3)

### Step 3: Verify Deployment

Once deployed, Render will give you a URL like:
```
https://quicksalon-backend.onrender.com
```

**Test your backend:**
```bash
curl https://quicksalon-backend.onrender.com/api/
```

**Expected Response:**
```json
{
  "message": "QuickSalon API",
  "version": "1.0.0"
}
```

### Step 4: Get Your Backend URL

Your backend URL will be:
```
https://quicksalon-backend.onrender.com
```

**📋 Copy this URL - you'll need it for the frontend!**

---

## 🔧 Environment Variables Required

| Variable | Value | Required |
|----------|-------|----------|
| `MONGO_URL` | MongoDB connection string | ✅ Yes |
| `DB_NAME` | quicksalon | ✅ Yes (default set) |
| `PORT` | Auto-set by Render | ❌ Auto |

---

## ⚙️ Configuration Details

### Python Version
- **Used**: Python 3.11
- **Set in**: `render.yaml`

### Dependencies (requirements.txt)
```
fastapi==0.115.6
uvicorn==0.34.0
motor==3.7.0
python-dotenv==1.0.1
pydantic==2.10.6
```

### API Endpoints
All endpoints are prefixed with `/api/`:
- `GET /api/` - Health check
- `POST /api/owner/login` - Owner authentication
- `POST /api/salon` - Create salon
- `GET /api/salons/nearby` - Get nearby salons
- `POST /api/queue/join` - Join queue
- And 20+ more endpoints...

---

## 🐛 Troubleshooting

### Issue 1: Build Failed
**Error**: `Could not install packages due to an OSError`

**Solution**: 
- Check requirements.txt has correct package names
- Ensure Python version is 3.11

### Issue 2: Application Failed to Start
**Error**: `Application startup failed`

**Solution**:
- Check MONGO_URL is set correctly
- Verify MongoDB Atlas IP whitelist includes 0.0.0.0/0
- Check MongoDB cluster is active

### Issue 3: 502 Bad Gateway
**Error**: Render shows 502 error

**Solution**:
- Check Render logs: Dashboard → Your Service → Logs
- Ensure `uvicorn` command is correct
- Verify PORT environment variable is used

### Issue 4: CORS Errors
**Error**: `blocked by CORS policy`

**Solution**:
- Backend already has `allow_origins=["*"]` for development
- For production, update `server.py`:
  ```python
  allow_origins=["https://your-frontend-domain.com"]
  ```

### Issue 5: MongoDB Connection Failed
**Error**: `connection refused` or `authentication failed`

**Solution**:
- Verify MONGO_URL format:
  ```
  mongodb+srv://username:password@cluster.mongodb.net/
  ```
- Check username and password are correct
- Ensure IP whitelist in MongoDB Atlas

---

## 📊 Render Free Tier Limits

| Resource | Limit |
|----------|-------|
| RAM | 512 MB |
| CPU | Shared |
| Bandwidth | 100 GB/month |
| Build Time | 15 min/month |
| **Cost** | **FREE** |

**Important Note:**
- Free tier services spin down after 15 minutes of inactivity
- First request after inactivity may take 30-60 seconds (cold start)
- For always-on service, upgrade to paid tier ($7/month)

---

## 🔒 Security Recommendations

### For Production:

1. **Change Admin Credentials**
   ```python
   # In server.py line 435
   # Replace hardcoded admin/admin123
   if data.username == os.getenv("ADMIN_USER") and data.password == os.getenv("ADMIN_PASS"):
   ```

2. **Restrict CORS**
   ```python
   # In server.py line 647
   allow_origins=["https://your-frontend-domain.netlify.app"]
   ```

3. **Use Environment Variables**
   - Add `ADMIN_USER` and `ADMIN_PASS` to Render environment

4. **Enable MongoDB Authentication**
   - MongoDB Atlas already uses authentication
   - Never share your connection string

---

## 📈 Monitoring & Logs

### View Logs
1. Go to Render Dashboard
2. Click your service
3. Click "Logs" tab
4. See real-time logs

### Metrics
- Dashboard shows CPU, Memory, Request counts
- Free tier has basic metrics

---

## 🔄 Updating Your Backend

### Method 1: Git Push (Recommended)
```bash
cd backend/
git add .
git commit -m "Update backend"
git push origin main
```
Render auto-deploys on push!

### Method 2: Manual Deploy
- Go to Render Dashboard
- Click "Manual Deploy" → "Deploy latest commit"

---

## ✅ Deployment Checklist

- [ ] MongoDB Atlas account created
- [ ] Free cluster created and running
- [ ] IP whitelist set to 0.0.0.0/0
- [ ] MongoDB connection string copied
- [ ] Backend deployed to Render
- [ ] MONGO_URL environment variable set
- [ ] Service is live (check URL)
- [ ] Test API endpoint works
- [ ] Backend URL copied for frontend

---

## 🎉 Next Steps

Once your backend is deployed:

1. **Copy your Render URL**
   ```
   https://quicksalon-backend.onrender.com
   ```

2. **Share it with me to update frontend**
   - I'll update the dist folder
   - Point frontend to your backend
   - Rebuild for Netlify

3. **Deploy frontend to Netlify**
   - Drag & drop dist folder
   - Your app is live!

---

## 📞 Support Resources

- **Render Docs**: https://render.com/docs
- **MongoDB Atlas**: https://docs.mongodb.com/atlas/
- **FastAPI**: https://fastapi.tiangolo.com/

---

## 💡 Cost Breakdown (FREE!)

| Service | Cost |
|---------|------|
| Render Backend | $0 (Free tier) |
| MongoDB Atlas | $0 (512MB free) |
| Netlify Frontend | $0 (100GB/month) |
| **Total** | **$0/month** |

**Your app costs nothing to run!** 🎉

---

## 🚨 Important Notes

1. **Cold Starts**: Free tier sleeps after 15 min. First request takes longer.
2. **Always-On**: Need instant response? Upgrade to $7/month paid tier.
3. **Database Backup**: MongoDB Atlas free tier doesn't include automatic backups.
4. **SSL/HTTPS**: Render provides free SSL automatically.

---

**Ready to deploy?** Follow the steps above and share your Render URL with me to update the frontend! 🚀
