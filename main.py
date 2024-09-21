from flask import Flask, request, jsonify
import hmac
import hashlib
from flask import Flask, request, jsonify
import hmac
import hashlib
import os
import logging
from dotenv import load_dotenv
import requests
import subprocess
import base64

load_dotenv()

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# GitHub App configuration
GITHUB_WEBHOOK_SECRET = os.getenv('GITHUB_WEBHOOK_SECRET', 'your_webhook_secret_here')
GITHUB_APP_ID = os.getenv('GITHUB_APP_ID')
GITHUB_PRIVATE_KEY = os.getenv('GITHUB_PRIVATE_KEY')
GITHUB_INSTALLATION_ID = os.getenv('GITHUB_INSTALLATION_ID')

def get_github_token():
    # Implement GitHub App authentication to get an access token
    # This is a placeholder and needs to be implemented
    return "github_token"

def fetch_repository_contents(owner, repo, path, ref='main'):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    params = {"ref": ref}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        logger.error(f"Failed to fetch repository contents: {response.text}")
        return None

def create_branch(owner, repo, branch_name, sha):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/git/refs"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "ref": f"refs/heads/{branch_name}",
        "sha": sha
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        return response.json()
    else:
        logger.error(f"Failed to create branch: {response.text}")
        return None

def update_file(owner, repo, path, message, content, sha, branch):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "sha": sha,
        "branch": branch
    }
    response = requests.put(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()
    else:
        logger.error(f"Failed to update file: {response.text}")
        return None

def create_pull_request(owner, repo, title, body, head, base):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "title": title,
        "body": body,
        "head": head,
        "base": base
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        return response.json()
    else:
        logger.error(f"Failed to create pull request: {response.text}")
        return None

def verify_webhook_signature(payload_body, signature_header):
    """Verify that the payload was sent from GitHub by validating SHA256."""
    if not signature_header:
        return False
    hash_object = hmac.new(GITHUB_WEBHOOK_SECRET.encode('utf-8'), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + hash_object.hexdigest()
    return hmac.compare_digest(expected_signature, signature_header)

@app.route('/', methods=['GET'])
def index():
    return jsonify({"message": "Hello, World!"})

@app.route('/webhook', methods=['POST'])
def webhook():
    signature = request.headers.get('X-Hub-Signature-256')
    payload = request.data

    if not verify_webhook_signature(payload, signature):
        return jsonify({"error": "Request signatures didn't match!"}), 403

    # Log the payload
    logger.info(f"Received webhook payload: {payload.decode('utf-8')}")

    event = request.headers.get('X-GitHub-Event')
    data = request.json

    if event == 'issues' and data['action'] == 'opened':
        issue = data['issue']
        repo = data['repository']
        owner = repo['owner']['login']
        repo_name = repo['name']

        # Fetch repository contents
        contents = fetch_repository_contents(owner, repo_name, 'README.md')
        if contents:
            file_content = base64.b64decode(contents['content']).decode('utf-8')
            new_content = file_content + f"\n\n## New Issue\n\n{issue['body']}"
            
            # Create a new branch
            branch_name = f"update-readme-issue-{issue['number']}"
            main_branch = repo['default_branch']
            main_sha = requests.get(f"https://api.github.com/repos/{owner}/{repo_name}/git/ref/heads/{main_branch}").json()['object']['sha']
            new_branch = create_branch(owner, repo_name, branch_name, main_sha)
            
            if new_branch:
                # Update README.md in the new branch
                update_result = update_file(
                    owner,
                    repo_name,
                    'README.md',
                    f'Update README with issue #{issue["number"]}',
                    new_content,
                    contents['sha'],
                    branch_name
                )
                
                if update_result:
                    # Create pull request
                    pr = create_pull_request(
                        owner,
                        repo_name,
                        f"Update README with issue #{issue['number']}",
                        f"This PR updates the README with the content from issue #{issue['number']}",
                        branch_name,
                        main_branch
                    )
                    
                    if pr:
                        return jsonify({"message": f"Pull request created: {pr['html_url']}"}), 200
                    else:
                        return jsonify({"error": "Failed to create pull request"}), 500
                else:
                    return jsonify({"error": "Failed to update file"}), 500
            else:
                return jsonify({"error": "Failed to create new branch"}), 500
        else:
            return jsonify({"error": "Failed to fetch repository contents"}), 500

    return jsonify({"message": "Received"}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)

