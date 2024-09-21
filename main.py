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
import jwt
import time
import zipfile
import io
import tempfile
import shutil
from aider.coders import Coder
from aider.models import Model
from aider.io import InputOutput

load_dotenv()

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# GitHub App configuration
GITHUB_WEBHOOK_SECRET = os.getenv('GITHUB_WEBHOOK_SECRET', 'your_webhook_secret_here')
GITHUB_APP_ID = os.getenv('GITHUB_APP_ID')
GITHUB_PRIVATE_KEY_PATH = os.getenv('GITHUB_PRIVATE_KEY_PATH', 'path/to/your/private-key.pem')
GITHUB_INSTALLATION_ID = os.getenv('GITHUB_INSTALLATION_ID')

# Read the private key from the PEM file
with open(GITHUB_PRIVATE_KEY_PATH, 'r') as key_file:
    GITHUB_PRIVATE_KEY = key_file.read()

def get_github_token():
    try:
        # Open PEM file and read the signing key
        with open(GITHUB_PRIVATE_KEY_PATH, 'rb') as pem_file:
            signing_key = pem_file.read()

        payload = {
            'iat': int(time.time()),
            'exp': int(time.time()) + 600,  # JWT expiration time (10 minutes maximum)
            'iss': GITHUB_APP_ID
        }

        # Create JWT
        jwt_token = jwt.encode(payload, signing_key, algorithm='RS256')

        # Get an installation access token
        headers = {
            'Authorization': f'Bearer {jwt_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        response = requests.post(
            f'https://api.github.com/app/installations/{GITHUB_INSTALLATION_ID}/access_tokens',
            headers=headers
        )

        response.raise_for_status()
        return response.json()['token']
    except FileNotFoundError:
        logger.error(f"Private key file not found: {GITHUB_PRIVATE_KEY_PATH}")
    except jwt.PyJWTError as e:
        logger.error(f"JWT encoding failed: {str(e)}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get GitHub token: {str(e)}")
    except KeyError:
        logger.error("Unexpected response format from GitHub API")
    except Exception as e:
        logger.error(f"Unexpected error in get_github_token: {str(e)}")
    
    return None

def download_repository(owner, repo, ref='main'):
    token = get_github_token()
    if not token:
        logger.error("Failed to get GitHub token")
        return None
    
    url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{ref}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download repository: {e}")
        return None

def extract_repository(zip_content):
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # The extracted content is in a subdirectory, so we need to find it
            extracted_dir = next(os.walk(temp_dir))[1][0]
            full_extracted_path = os.path.join(temp_dir, extracted_dir)
            
            # Create a new temporary directory to copy the contents
            with tempfile.TemporaryDirectory() as repo_dir:
                # Copy the contents to the new directory
                for item in os.listdir(full_extracted_path):
                    s = os.path.join(full_extracted_path, item)
                    d = os.path.join(repo_dir, item)
                    if os.path.isdir(s):
                        shutil.copytree(s, d)
                    else:
                        shutil.copy2(s, d)
                
                return repo_dir
    except Exception as e:
        logger.error(f"Failed to extract repository: {e}")
        return None

def read_file(repo_dir, file_path):
    full_path = os.path.join(repo_dir, file_path)
    try:
        with open(full_path, 'r') as file:
            return file.read()
    except Exception as e:
        logger.error(f"Failed to read file {file_path}: {e}")
        return None

def write_file(repo_dir, file_path, content):
    full_path = os.path.join(repo_dir, file_path)
    try:
        with open(full_path, 'w') as file:
            file.write(content)
        return True
    except Exception as e:
        logger.error(f"Failed to write file {file_path}: {e}")
        return False

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

def update_file(owner, repo, path, message, content, branch):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch
    }
    
    # First, get the current file to retrieve its SHA
    response = requests.get(url, headers=headers, params={"ref": branch})
    if response.status_code == 200:
        current_file = response.json()
        data["sha"] = current_file["sha"]
    elif response.status_code != 404:  # 404 means file doesn't exist yet
        logger.error(f"Failed to get current file: {response.text}")
        return None

    response = requests.put(url, headers=headers, json=data)
    if response.status_code in (200, 201):
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

def create_issue_comment(owner, repo, issue_number, body):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "body": body
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        return response.json()
    else:
        logger.error(f"Failed to create issue comment: {response.text}")
        return None

def verify_webhook_signature(payload_body, signature_header):
    """Verify that the payload was sent from GitHub by validating SHA256."""
    if not signature_header:
        return False
    hash_object = hmac.new(GITHUB_WEBHOOK_SECRET.encode('utf-8'), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + hash_object.hexdigest()
    return hmac.compare_digest(expected_signature, signature_header)

def do_coding_request(issue_title, issue_body, files_list, root_folder_path):
    model = Model("claude-3-5-sonnet-20240620")
    full_file_paths = [os.path.join(root_folder_path, file) for file in files_list]
    io = InputOutput(yes=True)
    coder = Coder.create(main_model=model, fnames=full_file_paths, io=io, use_git=False)

@app.route('/', methods=['GET'])
def index():
    return jsonify({"message": "Hello, World!"})

@app.route('/webhook', methods=['POST'])
def webhook():
    signature = request.headers.get('X-Hub-Signature-256')
    payload = request.data

    if not verify_webhook_signature(payload, signature):
        return jsonify({"error": "Request signatures didn't match!"}), 403

    logger.info(f"Received webhook payload: {payload.decode('utf-8')}")

    event = request.headers.get('X-GitHub-Event')
    data = request.json

    if event != 'issues' or data['action'] != 'opened':
        return jsonify({"message": "Received"}), 200

    issue = data['issue']
    repo = data['repository']
    owner = repo['owner']['login']
    repo_name = repo['name']

    zip_content = download_repository(owner, repo_name)
    if not zip_content:
        return jsonify({"error": "Failed to download repository"}), 500

    repo_dir = extract_repository(zip_content)
    if not repo_dir:
        return jsonify({"error": "Failed to extract repository"}), 500

    files_list = extract_files_list_from_issue(issue['body'])

    do_coding_request(issue['title'], issue['body'], files_list, repo_dir)

    changed_file_paths = get_changed_file_paths(repo_dir)

    branch_name = f"fix-issue-{issue['number']}"
    main_branch = repo['default_branch']
    main_sha = requests.get(f"https://api.github.com/repos/{owner}/{repo_name}/git/ref/heads/{main_branch}").json()['object']['sha']
    
    new_branch = create_branch(owner, repo_name, branch_name, main_sha)
    if not new_branch:
        return jsonify({"error": "Failed to create new branch"}), 500

    for file_path in changed_file_paths:
        content = read_file(repo_dir, file_path)
        if not content:
            return jsonify({"error": f"Failed to read file {file_path}"}), 500
        update_result = update_file(
            owner,
            repo_name,
            file_path,
            f'Update with issue #{issue["number"]}',
            content,
            branch_name
        )
        if not update_result:
            return jsonify({"error": f"Failed to update file {file_path}"}), 500

    pr = create_pull_request(
        owner,
        repo_name,
        f"Update README with issue #{issue['number']}",
        f"This PR updates the README with the content from issue #{issue['number']}",
        branch_name,
        main_branch
    )
    if not pr:
        return jsonify({"error": "Failed to create pull request"}), 500

    comment_body = f"I've created a pull request to update the README with this issue's content: {pr['html_url']}"
    comment = create_issue_comment(owner, repo_name, issue['number'], comment_body)

    if comment:
        return jsonify({"message": f"Pull request created and issue commented: {pr['html_url']}"}), 200
    else:
        return jsonify({"message": f"Pull request created, but failed to comment on issue: {pr['html_url']}"}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)

