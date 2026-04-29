# Legal Document Analyzer - AWS EC2 Deployment (2-Instance Setup)

This guide covers deploying the **Legal Document Analyzer** on **two separate AWS EC2 instances**: one for the backend (Flask API) and one for the frontend (Next.js).

---

## Architecture Overview

```
┌──────────────────────────────┐
│   Frontend EC2 (Instance 1)  │
│  - Next.js on Port 3000      │
│  - Nginx on Port 80          │
│  - PM2 (process manager)     │
└──────────────────────────────┘
              │
              │ (NEXT_PUBLIC_API_URL)
              ↓
┌──────────────────────────────┐
│   Backend EC2 (Instance 2)   │
│  - Flask on Port 5001        │
│  - Gunicorn (WSGI server)    │
│  - Systemd (process manager) │
└──────────────────────────────┘
              │
              ↓
    ┌─────────────────────┐
    │   MongoDB Atlas     │
    │   AWS S3 Bucket     │
    └─────────────────────┘
```

---

## Prerequisites

- AWS account with EC2 access
- 2 EC2 instances (Ubuntu 22.04, t3.micro or t3.small)
- Security groups configured for SSH (port 22), HTTP (port 80), HTTPS (port 443), and backend API (port 5001)
- GitHub repository with your code
- MongoDB Atlas connection string
- AWS S3 bucket with credentials

---

## Part 1: Backend Deployment (Flask + Gunicorn)

### 1.1 Launch Backend EC2 Instance

1. **Create EC2 Instance:**
   - OS: Ubuntu 22.04 LTS
   - Instance type: t3.micro or t3.small
   - Storage: 25–30 GB EBS
   - Security group: Allow SSH (22), HTTP (80), HTTPS (443), and custom port 5001

2. **Assign Elastic IP** (optional but recommended for stability)

3. **SSH into the instance:**
   ```bash
   ssh -i your-key.pem ubuntu@<backend-public-ip>
   #update the your-key.pem 
   ```

### 1.2 Install Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python, pip, and system dependencies
sudo apt install -y python3 python3-pip python3-venv git nginx

# Clone your repository
git clone https://github.com/psrivarshika00/Legal-Document-Analyzer---final-project-.git
cd Legal-Document-Analyzer---final-project-/backend
```

### 1.3 Create Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 1.4 Set Up Environment Variables

Create a `.env` file in the `backend/` directory:

```bash
cat > .env << 'EOF'
MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>/?retryWrites=true&w=majority
DB_NAME=legal_analyzer
AWS_REGION=us-east-1
S3_BUCKET_NAME=<your-s3-bucket>
AWS_ACCESS_KEY_ID=<your-access-key>
AWS_SECRET_ACCESS_KEY=<your-secret-key>
PORT=5001
EOF
```

### 1.5 Test Flask Locally

```bash
python app.py
# Should see: "Running on http://127.0.0.1:5001"
# Exit with Ctrl+C
```

### 1.6 Set Up Gunicorn + Systemd

**Install Gunicorn:**
```bash
pip install gunicorn
```

**Create systemd service file:**
```bash
sudo tee /etc/systemd/system/legal-analyzer-backend.service > /dev/null << 'EOF'
[Unit]
Description=Legal Analyzer Backend
After=network.target

[Service]
Type=notify
User=ubuntu
WorkingDirectory=/home/ubuntu/Legal-Document-Analyzer---final-project-/backend
Environment="PATH=/home/ubuntu/Legal-Document-Analyzer---final-project-/backend/venv/bin"
EnvironmentFile=/home/ubuntu/Legal-Document-Analyzer---final-project-/backend/.env
ExecStart=/home/ubuntu/Legal-Document-Analyzer---final-project-/backend/venv/bin/gunicorn --bind 0.0.0.0:5001 --workers 4 wsgi:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

**Enable and start the service:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable legal-analyzer-backend
sudo systemctl start legal-analyzer-backend
```

**Verify backend is running:**
```bash
sudo systemctl status legal-analyzer-backend
curl http://127.0.0.1:5001/
```

### 1.7 Configure Nginx (Reverse Proxy)

**Create Nginx config for backend:**
```bash
sudo tee /etc/nginx/sites-available/backend << 'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
```

**Enable and test Nginx:**
```bash
sudo ln -sf /etc/nginx/sites-available/backend /etc/nginx/sites-enabled/backend
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

**Test backend via Nginx:**
```bash
curl http://127.0.0.1
```

### 1.8 Verify Backend from Local Machine

```bash
curl http://<backend-public-ip>:5001/
# Should return a response from your Flask app
```

---

## Part 2: Frontend Deployment (Next.js + PM2)

### 2.1 Launch Frontend EC2 Instance

1. **Create EC2 Instance:**
   - OS: Ubuntu 22.04 LTS
   - Instance type: t3.micro or t3.small
   - Storage: 25–30 GB EBS
   - Security group: Allow SSH (22), HTTP (80), HTTPS (443)

2. **Assign Elastic IP** (optional but recommended)

3. **SSH into the instance:**
   ```bash
   ssh -i your-key.pem ubuntu@<frontend-public-ip>
   ```

### 2.2 Install Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Node.js, npm, git, and nginx
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs git nginx

# Clone your repository
git clone https://github.com/psrivarshika00/Legal-Document-Analyzer---final-project-.git
cd Legal-Document-Analyzer---final-project-/frontend
```

### 2.3 Set Up Environment Variables

Create a `.env.production` file in the `frontend/` directory with your backend URL:

```bash
cat > .env.production << 'EOF'
NEXT_PUBLIC_API_URL=http://<backend-public-ip>:5001
EOF
```

**Replace `<backend-public-ip>` with your backend EC2's public IP address.**

### 2.4 Build Frontend

```bash
npm install
npm run build
```

**Note:** If you run out of memory, create swap space:
```bash
sudo dd if=/dev/zero of=/swapfile bs=1G count=2
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
# Then try: npm run build
```

### 2.5 Set Up PM2 (Process Manager)

**Install PM2 globally:**
```bash
sudo npm install -g pm2
```

**Start frontend with PM2:**
```bash
pm2 start npm --name legal-analyzer-frontend -- start
pm2 save
sudo env PATH=$PATH:/usr/bin /usr/lib/node_modules/pm2/bin/pm2 startup systemd -u ubuntu --hp /home/ubuntu
```

**Verify PM2:**
```bash
pm2 status
pm2 logs legal-analyzer-frontend
```

### 2.6 Configure Nginx (Reverse Proxy)

**Create Nginx config for frontend:**
```bash
sudo tee /etc/nginx/sites-available/frontend << 'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF
```

**Enable and test Nginx:**
```bash
sudo ln -sf /etc/nginx/sites-available/frontend /etc/nginx/sites-enabled/frontend
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

### 2.7 Verify Frontend from Local Machine

```bash
curl http://<frontend-public-ip>
# Or open in browser: http://<frontend-public-ip>
```

---

## Part 3: Security Groups Setup

### Backend Security Group

| Type       | Protocol | Port Range | Source              |
|------------|----------|------------|---------------------|
| SSH        | TCP      | 22         | Your IP / 0.0.0.0/0 |
| HTTP       | TCP      | 80         | 0.0.0.0/0           |
| HTTPS      | TCP      | 443        | 0.0.0.0/0           |
| Custom TCP | TCP      | 5001       | Frontend SG / 0.0.0/0 |

### Frontend Security Group

| Type   | Protocol | Port Range | Source      |
|--------|----------|------------|-------------|
| SSH    | TCP      | 22         | Your IP / 0.0.0.0/0 |
| HTTP   | TCP      | 80         | 0.0.0.0/0   |
| HTTPS  | TCP      | 443        | 0.0.0.0/0   |

---

## Part 4: Testing & Verification

### Test Backend

```bash
# From your local machine
curl http://<backend-public-ip>:5001/
curl http://<backend-public-ip>:5001/health  # if endpoint exists

# From frontend EC2
curl http://<backend-private-ip>:5001/
```

### Test Frontend

```bash
# From your local machine
curl http://<frontend-public-ip>
# Or open in browser: http://<frontend-public-ip>

# Check PM2 status on frontend EC2
pm2 status
pm2 logs

# Check Nginx status on frontend EC2
sudo systemctl status nginx
sudo nginx -t
```

### Test API Call from Frontend

In your browser console on the frontend, run:
```javascript
fetch('http://<frontend-public-ip>/api/some-endpoint')
  .then(r => r.json())
  .then(console.log)
```

---

## Part 5: Maintenance & Troubleshooting

### Check Service Status

**Backend:**
```bash
sudo systemctl status legal-analyzer-backend
sudo systemctl restart legal-analyzer-backend
sudo journalctl -u legal-analyzer-backend -f
```

**Frontend:**
```bash
pm2 status
pm2 logs legal-analyzer-frontend
pm2 restart legal-analyzer-frontend
```

### View Logs

**Backend:**
```bash
tail -f /home/ubuntu/Legal-Document-Analyzer---final-project-/backend/logs/app.log  # if you have logs
sudo journalctl -u legal-analyzer-backend -n 100
```

**Frontend:**
```bash
pm2 logs
```

### Restart Services

```bash
# Backend
ssh -i your-key.pem ubuntu@<backend-public-ip>
sudo systemctl restart legal-analyzer-backend

# Frontend
ssh -i your-key.pem ubuntu@<frontend-public-ip>
pm2 restart legal-analyzer-frontend
```

### Update Code from GitHub

**Backend:**
```bash
cd /home/ubuntu/Legal-Document-Analyzer---final-project-/backend
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart legal-analyzer-backend
```

**Frontend:**
```bash
cd /home/ubuntu/Legal-Document-Analyzer---final-project-/frontend
git pull origin main
npm install
npm run build
pm2 restart legal-analyzer-frontend
```

---

## Part 6: Environment Variables Summary

### Backend EC2 (.env)
```env
MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>/?retryWrites=true&w=majority
DB_NAME=legal_analyzer
AWS_REGION=us-east-1
S3_BUCKET_NAME=<your-s3-bucket>
AWS_ACCESS_KEY_ID=<your-access-key>
AWS_SECRET_ACCESS_KEY=<your-secret-key>
PORT=5001
```

### Frontend EC2 (.env.production)
```env
NEXT_PUBLIC_API_URL=http://<backend-public-ip>:5001
```

---

## Part 7: Quick Reference Commands

### Backend EC2
```bash
# SSH
ssh -i your-key.pem ubuntu@<backend-public-ip>

# Check service
sudo systemctl status legal-analyzer-backend

# View logs
sudo journalctl -u legal-analyzer-backend -f

# Restart
sudo systemctl restart legal-analyzer-backend

# Test API
curl http://127.0.0.1:5001/
```

### Frontend EC2
```bash
# SSH
ssh -i your-key.pem ubuntu@<frontend-public-ip>

# Check PM2
pm2 status

# View logs
pm2 logs

# Restart
pm2 restart legal-analyzer-frontend

# Test app
curl http://127.0.0.1:3000
```

---

## Part 8: Restart Services After Stopping Instance

When you restart an EC2 instance after stopping it, services are configured to auto-start. However, use these commands to manually verify and restart if needed.

### Restart Backend Service

```bash
ssh -i your-key.pem ubuntu@<backend-public-ip>

# Start the backend service
sudo systemctl start legal-analyzer-backend

# Verify it's running
sudo systemctl status legal-analyzer-backend

# Start Nginx
sudo systemctl start nginx

# Test backend is working
curl http://127.0.0.1:5001/
```

### Restart Frontend Service

```bash
ssh -i your-key.pem ubuntu@<frontend-public-ip>

# Go to frontend directory
cd /home/ubuntu/Legal-Document-Analyzer---final-project-/frontend

# Start or restart PM2
pm2 start npm --name legal-analyzer-frontend -- start

# Verify PM2 is running
pm2 status

# Start Nginx
sudo systemctl start nginx

# Test frontend is working
curl http://127.0.0.1:3000
```

### Test Services from Local Machine

```bash
# Test backend
curl http://<backend-public-ip>:5001/

# Test frontend (open in browser)
http://<frontend-public-ip>
```

---

---

## Part 9: QUICK REDEPLOYMENT STEPS (Current IPs)

**Current Active IPs:**
- **Backend EC2**: `54.160.22.184:5001`
- **Frontend EC2**: `44.222.104.163`
- **Key file**: `/Users/varshikamac/Downloads/legal-keypair.pem`

### Step 1: Build and Push Frontend Locally

```bash
cd /Users/varshikamac/Desktop/final_project/frontend
npm run build
cd /Users/varshikamac/Desktop/final_project
git add .
git commit -m "Rebuild frontend"
git push origin main
```

### Step 2: SSH into Frontend EC2 and Redeploy

```bash
ssh -i /Users/varshikamac/Downloads/legal-keypair.pem ubuntu@44.222.104.163 << 'EOFCMD'
cd /home/ubuntu/Legal-Document-Analyzer---final-project-/frontend
git pull origin main
npm install
npm run build
pm2 restart legal-analyzer-frontend
sleep 2
pm2 status
EOFCMD
```

### Step 3: Update Backend API URL (if backend IP changes)

If backend IP changes, update this file on frontend EC2:

```bash
ssh -i /Users/varshikamac/Downloads/legal-keypair.pem ubuntu@44.222.104.163 << 'EOFCMD'
cat > /home/ubuntu/Legal-Document-Analyzer---final-project-/frontend/.env.production << 'EOF'
NEXT_PUBLIC_API_URL=http://54.160.22.184:5001
EOF
cat /home/ubuntu/Legal-Document-Analyzer---final-project-/frontend/.env.production
EOFCMD
```

Then rebuild:

```bash
ssh -i /Users/varshikamac/Downloads/legal-keypair.pem ubuntu@44.222.104.163 << 'EOFCMD'
cd /home/ubuntu/Legal-Document-Analyzer---final-project-/frontend
npm run build
pm2 restart legal-analyzer-frontend
pm2 status
EOFCMD
```

### Step 4: Check Backend is Running

```bash
ssh -i /Users/varshikamac/Downloads/legal-keypair.pem ubuntu@54.160.22.184 << 'EOFCMD'
sudo systemctl status legal-analyzer-backend
sudo systemctl start legal-analyzer-backend || true
curl http://127.0.0.1:5001/
EOFCMD
```

### Step 5: Verify Both Services

```bash
# Test backend
curl http://54.160.22.184:5001/

# Test frontend (in browser or curl)
curl http://44.222.104.163 | head -c 200
```

---

## FILES TO UPDATE WHEN IPs CHANGE

### 1. Local Frontend `.env.production`
**Location**: `/Users/varshikamac/Desktop/final_project/frontend/.env.production`
**Current Content**:
```env
NEXT_PUBLIC_API_URL=http://54.160.22.184:5001
```
**If backend IP changes**: Update this file with new backend IP, then:
```bash
cd /Users/varshikamac/Desktop/final_project
git add frontend/.env.production
git commit -m "Update backend API URL"
git push origin main
npm run build
```

### 2. Remote Frontend `.env.production` (on EC2)
**Location**: `/home/ubuntu/Legal-Document-Analyzer---final-project-/frontend/.env.production`
**Auto-updated by**: `git pull origin main` on EC2, then rebuild with `npm run build`

### 3. DEPLOYMENT.md (this file)
**Location**: `/Users/varshikamac/Desktop/final_project/DEPLOYMENT.md`
**Update when IPs change**:
- Backend IP: `54.160.22.184`
- Frontend IP: `44.222.104.163`

---

## Conclusion

Your **Legal Document Analyzer** is now deployed on two separate EC2 instances:
- **Backend**: Flask API running on `http://54.160.22.184:5001`
- **Frontend**: Next.js app running on `http://44.222.104.163`

Both instances are configured for automatic startup and restart on failure. Use Part 9 for quick redeployment steps.
