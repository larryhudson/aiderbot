# Deployment Instructions for Ubuntu VPS + Nginx

This document provides instructions for deploying the application on an Ubuntu VPS using Gunicorn, Nginx, Certbot, and Supervisor.

## Prerequisites

- Ubuntu VPS
- Domain name pointing to your VPS IP address

## Deployment Steps

1. SSH into your Ubuntu VPS.

2. Clone the repository:
   ```
   git clone https://github.com/your-username/your-repo.git
   cd your-repo
   ```

3. Run the deployment script:
   ```
   bash deploy_script.sh
   ```

   This script will guide you through the installation and configuration process.

4. Follow the prompts in the script to install and configure the necessary components.

5. Once the script completes, your application should be up and running.

## Updating the Application

To update the application when changes are made to the source code:

1. SSH into your Ubuntu VPS.

2. Navigate to your project directory:
   ```
   cd /path/to/your-repo
   ```

3. Pull the latest changes:
   ```
   git pull origin main
   ```

4. Restart the Gunicorn service:
   ```
   sudo supervisorctl restart mathweb
   ```

## Troubleshooting

- Check Nginx logs: `sudo tail -f /var/log/nginx/error.log`
- Check your application logs: `sudo tail -f /var/log/mathweb.err.log` and `sudo tail -f /var/log/mathweb.out.log`
- Ensure Nginx configuration is correct: `sudo nginx -t`
- Restart Nginx: `sudo systemctl restart nginx`
- Check Gunicorn status: `sudo supervisorctl status mathweb`
- Restart the application: `sudo supervisorctl restart mathweb`

If you encounter any issues, please refer to the respective documentation for Nginx, Gunicorn, Certbot, and Supervisor.
