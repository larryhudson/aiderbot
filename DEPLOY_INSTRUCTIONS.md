# Deployment Instructions

This document provides instructions for deploying the application using two methods:
1. Ubuntu VPS + Nginx
2. Docker + Coolify

## Method 1: Ubuntu VPS + Nginx

### Prerequisites

- Ubuntu VPS
- Domain name pointing to your VPS IP address

### Deployment Steps

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

### Updating the Application

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
   sudo supervisorctl restart your_domain_name
   ```

### Troubleshooting

- Check Nginx logs: `sudo tail -f /var/log/nginx/error.log`
- Check your application logs: `sudo tail -f /var/log/your_domain_name.err.log` and `sudo tail -f /var/log/your_domain_name.out.log`
- Ensure Nginx configuration is correct: `sudo nginx -t`
- Restart Nginx: `sudo systemctl restart nginx`
- Check Gunicorn status: `sudo supervisorctl status your_domain_name`
- Restart the application: `sudo supervisorctl restart your_domain_name`

If you encounter any issues, please refer to the respective documentation for Nginx, Gunicorn, Certbot, and Supervisor.

## Method 2: Docker + Coolify

### Prerequisites

- Coolify account and server set up
- Docker and Docker Compose installed on your local machine (for testing)

### Deployment Steps

1. Clone the repository:
   ```
   git clone https://github.com/your-username/your-repo.git
   cd your-repo
   ```

2. Make sure you have a `docker-compose.yml` file in your project root. If not, create one using the provided template.

3. Test the Docker setup locally:
   ```
   docker-compose up --build
   ```

4. Once you've confirmed that the Docker setup works locally, push your changes to your Git repository.

5. Log in to your Coolify dashboard.

6. Create a new service and select "Docker Compose" as the deployment method.

7. Connect your Git repository to Coolify.

8. Configure the deployment settings in Coolify:
   - Set the Docker Compose file path (usually `./docker-compose.yml`)
   - Configure any necessary environment variables
   - Set up your domain and SSL settings

9. Deploy your application using Coolify's deployment options.

### Updating the Application

To update the application when changes are made to the source code:

1. Push your changes to the Git repository connected to Coolify.

2. Coolify will automatically detect the changes and trigger a new deployment.

3. Monitor the deployment process in the Coolify dashboard.

### Troubleshooting

- Check the Coolify dashboard for deployment logs and error messages.
- Ensure that your `docker-compose.yml` file is correctly formatted and all necessary services are defined.
- Verify that all required environment variables are set in the Coolify dashboard.
- If you encounter issues, you can SSH into the Coolify server and check Docker logs:
  ```
  docker logs <container_name>
  ```

For more information on using Coolify with Docker Compose, refer to the Coolify documentation: https://coolify.io/docs/knowledge-base/docker/compose/
