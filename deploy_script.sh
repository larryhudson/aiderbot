#!/bin/bash

# Function to prompt user for yes/no input
prompt_yes_no() {
    while true; do
        read -p "$1 (y/n): " yn
        case $yn in
            [Yy]* ) return 0;;
            [Nn]* ) return 1;;
            * ) echo "Please answer yes or no.";;
        esac
    done
}

echo "Welcome to the deployment script for your application!"
echo "This script will help you set up your Ubuntu VPS with Nginx, Gunicorn, Certbot, and Supervisor."

# Update system
if prompt_yes_no "Do you want to update your system?"; then
    echo "Updating system..."
    sudo apt update && sudo apt upgrade -y
fi

# Install dependencies
if prompt_yes_no "Do you want to install Python, Nginx, and Certbot?"; then
    echo "Installing dependencies..."
    sudo apt install python3 python3-pip python3-venv nginx certbot python3-certbot-nginx -y
fi

# Install Supervisor
if prompt_yes_no "Do you want to install Supervisor?"; then
    echo "Installing Supervisor..."
    sudo apt install supervisor -y
fi

# Set up virtual environment and install requirements
if prompt_yes_no "Do you want to set up a virtual environment and install requirements?"; then
    echo "Setting up virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    pip install gunicorn uvicorn
fi

# Configure Nginx
if prompt_yes_no "Do you want to configure Nginx?"; then
    echo "Configuring Nginx..."
    read -p "Enter your domain name: " domain_name
    sudo tee /etc/nginx/sites-available/$domain_name <<EOF
server {
    server_name $domain_name;

    location / {
        proxy_pass http://unix:/tmp/$domain_name.sock;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
    sudo ln -s /etc/nginx/sites-available/$domain_name /etc/nginx/sites-enabled/
    sudo nginx -t && sudo systemctl restart nginx
fi

# Set up SSL with Certbot
if prompt_yes_no "Do you want to set up SSL with Certbot?"; then
    echo "Setting up SSL..."
    sudo certbot --nginx -d $domain_name
fi

# Configure Gunicorn and Supervisor
if prompt_yes_no "Do you want to configure Gunicorn and Supervisor?"; then
    echo "Configuring Gunicorn and Supervisor..."
    read -p "Enter the full path to your project directory: " project_path
    read -p "Enter your username: " username
    sudo tee /etc/supervisor/conf.d/mathweb.conf <<EOF
[program:$domain_name]
directory=$project_path
command=$project_path/venv/bin/gunicorn mathweb.flask.app:app -w 4 -k uvicorn.workers.UvicornWorker -b unix:/tmp/$domain_name.sock
user=$username
autostart=true
autorestart=true
stderr_logfile=/var/log/$domain_name.err.log
stdout_logfile=/var/log/$domain_name.out.log
EOF
    sudo supervisorctl reread
    sudo supervisorctl update
    sudo supervisorctl start $domain_name
fi

echo "Deployment script completed!"
echo "Please review the DEPLOY_INSTRUCTIONS.md file for additional information and troubleshooting tips."
