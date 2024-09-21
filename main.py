from aider.repo import GitRepo
from flask import Flask, request, jsonify
import hmac
import hashlib
import re
from flask import Flask, request, jsonify
import hmac
import hashlib
import os
import logging
from dotenv import load_dotenv
import requests
import subprocess
import json
import base64
import jwt
import time
import zipfile
import io
import tempfile
import shutil
import filecmp
import uuid
from aider.coders import Coder
from aider.models import Model
from aider.io import InputOutput

load_dotenv()

def get_changed_file_paths(original_dir, working_dir):
    """
    Compare two directories and return a list of files that have changed.
    """
    changed_files = []
    comparison = filecmp.dircmp(original_dir, working_dir)
    
    def recurse_and_compare(dcmp):
        for name in dcmp.diff_files:
            changed_files.append(os.path.relpath(os.path.join(dcmp.right, name), working_dir))
        for sub_dcmp in dcmp.subdirs.values():
            recurse_and_compare(sub_dcmp)
    
    recurse_and_compare(comparison)
    return changed_files

app = Flask(__name__)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("debug.log"),
        logging.StreamHandler()
    ]
)
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

def extract_repository(zip_content, temp_dir):
    try:
        repo_dir = os.path.join(temp_dir, f'repo_{uuid.uuid4().hex}')
        os.makedirs(repo_dir, exist_ok=True)

        with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_ref:
            zip_ref.extractall(repo_dir)
        
        # The extracted content is in a subdirectory, so we need to find it
        extracted_dir = next(os.walk(repo_dir))[1][0]
        full_extracted_path = os.path.join(repo_dir, extracted_dir)
        
        # Move the contents to the repo_dir
        for item in os.listdir(full_extracted_path):
            s = os.path.join(full_extracted_path, item)
            d = os.path.join(repo_dir, item)
            shutil.move(s, d)
        
        # Remove the now-empty subdirectory
        os.rmdir(full_extracted_path)
        
        # Initialize git repository
        subprocess.run(['git', 'init'], cwd=repo_dir, check=True)
        logger.info(f"Initialized git repository in {repo_dir}")

        # Make initial commit
        subprocess.run(['git', 'add', '-A'], cwd=repo_dir, check=True)
        subprocess.run(['git', 'commit', '-m', 'initial'], cwd=repo_dir, check=True)

        
        return repo_dir
    except Exception as e:
        logger.error(f"Failed to extract repository or initialize git: {e}")
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

def create_pull_request_for_issue(owner, repo_name, issue):
    logger.info(f"Processing issue #{issue['number']} for {owner}/{repo_name}")

    # Create a temporary directory within the current working directory
    temp_dir = tempfile.mkdtemp(dir=os.getcwd(), prefix='repo_')
    logger.info(f"Created temporary directory: {temp_dir}")

    try:
        zip_content = download_repository(owner, repo_name)
        if not zip_content:
            logger.error("Failed to download repository")
            return {"error": "Failed to download repository"}, 500

        logger.info("Repository downloaded successfully")

        repo_dir = extract_repository(zip_content, temp_dir)
        if not repo_dir:
            logger.error("Failed to extract repository")
            return {"error": "Failed to extract repository"}, 500

        logger.info(f"Repository extracted to {repo_dir}")

        # Create a copy of the original repository
        original_repo_dir = os.path.join(temp_dir, f'original_{uuid.uuid4().hex}')
        shutil.copytree(repo_dir, original_repo_dir)
        logger.info(f"Created original repository copy at {original_repo_dir}")

        files_list = extract_files_list_from_issue(issue['body'])
        logger.info(f"Extracted files list from issue: {files_list}")

        # Prepare the prompt
        prompt = f"Please help me resolve this issue.\n\nIssue Title: {issue['title']}\n\nIssue Body: {issue['body']}"
        logger.info("Prepared prompt for coding request")

        logger.info("Starting coding request")
        do_coding_request(prompt, files_list, repo_dir)
        logger.info("Coding request completed")

        changed_file_paths = get_changed_file_paths(original_repo_dir, repo_dir)
        logger.info(f"Changed files: {changed_file_paths}")

        # Clean up the original copy
        shutil.rmtree(original_repo_dir)
        logger.info("Cleaned up original repository copy")

        branch_name = f"fix-issue-{issue['number']}"
        main_branch = requests.get(f"https://api.github.com/repos/{owner}/{repo_name}").json()['default_branch']
        main_sha = requests.get(f"https://api.github.com/repos/{owner}/{repo_name}/git/ref/heads/{main_branch}").json()['object']['sha']
        
        logger.info(f"Creating new branch: {branch_name}")
        new_branch = create_branch(owner, repo_name, branch_name, main_sha)
        if not new_branch:
            logger.error("Failed to create new branch")
            return {"error": "Failed to create new branch"}, 500

        logger.info("New branch created successfully")

        for file_path in changed_file_paths:
            logger.info(f"Processing changed file: {file_path}")
            content = read_file(repo_dir, file_path)
            if not content:
                logger.error(f"Failed to read file {file_path}")
                return {"error": f"Failed to read file {file_path}"}, 500
            update_result = update_file(
                owner,
                repo_name,
                file_path,
                f'Update with issue #{issue["number"]}',
                content,
                branch_name
            )
            if not update_result:
                logger.error(f"Failed to update file {file_path}")
                return {"error": f"Failed to update file {file_path}"}, 500
            logger.info(f"File {file_path} updated successfully")

        logger.info("Creating pull request")
        pr = create_pull_request(
            owner,
            repo_name,
            f"Fix issue #{issue['number']}",
            f"This PR addresses the changes requested in issue #{issue['number']}",
            branch_name,
            main_branch
        )
        if not pr:
            logger.error("Failed to create pull request")
            return {"error": "Failed to create pull request"}, 500

        logger.info(f"Pull request created: {pr['html_url']}")

        comment_body = f"I've created a pull request to address this issue: {pr['html_url']}"
        logger.info("Adding comment to the issue")
        comment = create_issue_comment(owner, repo_name, issue['number'], comment_body)

        if comment:
            logger.info("Comment added successfully")
            return {"message": f"Pull request created and issue commented: {pr['html_url']}"}, 200
        else:
            logger.warning("Failed to add comment to the issue")
            return {"message": f"Pull request created, but failed to comment on issue: {pr['html_url']}"}, 200

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        return {"error": "An internal error occurred"}, 500

    finally:
        # Clean up the temporary directory
        shutil.rmtree(temp_dir)
        logger.info(f"Cleaned up temporary directory: {temp_dir}")

def handle_pr_review_comment(owner, repo_name, pull_request, comment):
    logger.info(f"Processing PR review comment for PR #{pull_request['number']} in {owner}/{repo_name}")

    if 'LGTM' in comment['body']:
        logger.info("Comment contains 'LGTM', no action needed")
        return {"message": "Comment acknowledged, no action needed"}, 200

    try:
        # Get the original issue
        issue_number = extract_issue_number_from_pr_title(pull_request['title'])
        logger.info(f"Extracted issue number: {issue_number}")
        if not issue_number:
            logger.error("Failed to extract issue number from PR title")
            return {"error": "Failed to extract issue number from PR title"}, 500

        issue = get_issue(owner, repo_name, issue_number)
        logger.info(f"Retrieved issue: {issue['number'] if issue else None}")
        if not issue:
            logger.error(f"Failed to get issue #{issue_number}")
            return {"error": f"Failed to get issue #{issue_number}"}, 500

        # Get the PR diff
        pr_diff = get_pr_diff(owner, repo_name, pull_request['number'])
        logger.info(f"Retrieved PR diff: {'Success' if pr_diff else 'Failed'}")
        if not pr_diff:
            logger.error("Failed to get PR diff")
            return {"error": "Failed to get PR diff"}, 500

        # Build the prompt
        prompt = build_prompt(issue, pr_diff, comment['body'])
        logger.info("Built prompt for coding request")

        # Create a temporary directory
        temp_dir = tempfile.mkdtemp(dir=os.getcwd(), prefix='repo_')
        logger.info(f"Created temporary directory: {temp_dir}")

        try:
            # Check if pull_request['head']['ref'] is set
            if 'head' not in pull_request or 'ref' not in pull_request['head']:
                logger.error("pull_request['head']['ref'] is not set")
                return {"error": "Invalid pull request data"}, 500
            logger.info(f"pull_request['head']['ref'] is set to: {pull_request['head']['ref']}")

            # Download and extract the repository
            zip_content = download_repository(owner, repo_name, pull_request['head']['ref'])
            logger.info(f"Downloaded repository: {'Success' if zip_content else 'Failed'}")
            if not zip_content:
                logger.error("Failed to download repository")
                return {"error": "Failed to download repository"}, 500

            repo_dir = extract_repository(zip_content, temp_dir)
            logger.info(f"Extracted repository to: {repo_dir}")
            if not repo_dir:
                logger.error("Failed to extract repository")
                return {"error": "Failed to extract repository"}, 500

            # Get the list of files changed in the PR
            changed_pr_files = get_pr_changed_files(owner, repo_name, pull_request['number'])
            logger.info(f"Files changed in PR: {changed_pr_files}")

            mentioned_files = extract_files_list_from_issue(comment['body'])
            logger.info(f"Files mentioned in comment: {mentioned_files}")

            files_list = list(set(changed_pr_files + mentioned_files))
            logger.info(f"Combined files list: {files_list}")

            # Do the coding request
            logger.info("Starting coding request")
            do_coding_request(prompt, files_list, repo_dir)
            logger.info("Completed coding request")

            # Get the changed files
            changed_file_paths = get_changed_file_paths(repo_dir, repo_dir)  # Compare with itself to get all changes
            logger.info(f"Files changed after coding request: {changed_file_paths}")

            # Update the files in the PR branch
            for file_path in changed_file_paths:
                logger.info(f"Processing file: {file_path}")
                content = read_file(repo_dir, file_path)
                if not content:
                    logger.error(f"Failed to read file {file_path}")
                    return {"error": f"Failed to read file {file_path}"}, 500
                logger.info(f"File content read successfully: {file_path}")
                update_result = update_file(
                    owner,
                    repo_name,
                    file_path,
                    f'Update PR #{pull_request["number"]} based on review comment',
                    content,
                    pull_request['head']['ref']
                )
                if not update_result:
                    logger.error(f"Failed to update file {file_path}")
                    return {"error": f"Failed to update file {file_path}"}, 500
                logger.info(f"File {file_path} updated successfully")

            # Add a comment to the PR
            comment_body = "I've updated the PR based on the review comment. Please check the changes."
            pr_comment = create_pr_comment(owner, repo_name, pull_request['number'], comment_body)
            if not pr_comment:
                logger.warning("Failed to add comment to the PR")
            else:
                logger.info("Added comment to PR successfully")

            return {"message": "PR updated based on review comment"}, 200

        finally:
            # Clean up the temporary directory
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temporary directory: {temp_dir}")

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        logger.exception("Full traceback:")
        return {"error": "An internal error occurred"}, 500

def extract_issue_number_from_pr_title(title):
    match = re.search(r'#(\d+)', title)
    return int(match.group(1)) if match else None

def get_issue(owner, repo, issue_number):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        logger.error(f"Failed to get issue: {response.text}")
        return None

def get_pr_diff(owner, repo, pr_number):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.diff"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.text
    else:
        logger.error(f"Failed to get PR diff: {response.text}")
        return None

def build_prompt(issue, pr_diff, review_comment):
    return f"""
Please help me address the following review comment on a pull request:

Original Issue:
Title: {issue['title']}
Body: {issue['body']}

Here is the original diff for the pull request:
{pr_diff}

Here is the review comment:
{review_comment}

Please make changes to address this review comment.
"""

def get_pr_changed_files(owner, repo, pr_number):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return [file['filename'] for file in response.json()]
    else:
        logger.error(f"Failed to get PR changed files: {response.text}")
        return []

def create_pr_comment(owner, repo, pr_number, body):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
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
        logger.error(f"Failed to create PR comment: {response.text}")
        return None

def extract_files_list_from_issue(issue_body):
    files_list = []
    files_section_started = False
    for line in issue_body.split('\n'):
        if line.strip() == 'Files:':
            files_section_started = True
            continue
        if files_section_started:
            if line.strip().startswith('- '):
                files_list.append(line.strip()[2:])
            elif line.strip() == '':
                break
            else:
                break
    return files_list

def verify_webhook_signature(payload_body, signature_header):
    """Verify that the payload was sent from GitHub by validating SHA256."""
    logger.info("Verifying webhook signature")
    if not signature_header:
        logger.warning("No signature header provided")
        return False
    hash_object = hmac.new(GITHUB_WEBHOOK_SECRET.encode('utf-8'), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + hash_object.hexdigest()
    result = hmac.compare_digest(expected_signature, signature_header)
    logger.info(f"Signature verification result: {result}")
    return result

def do_coding_request(prompt, files_list, root_folder_path):
    logger.info("Starting coding request")
    logger.info(f"Files List: {files_list}")
    
    model = Model("claude-3-5-sonnet-20240620")
    full_file_paths = [os.path.join(root_folder_path, file) for file in files_list]
    io = InputOutput(yes=True)
    git_repo = GitRepo(io, full_file_paths, root_folder_path)
    coder = Coder.create(main_model=model, fnames=full_file_paths, io=io, repo=git_repo)

    logger.info("Running coder with prompt")
    coder.run(prompt)
    logger.info("Coding request completed")


@app.route('/', methods=['GET'])
def index():
    return jsonify({"message": "Hello, World!"})

@app.route('/webhook', methods=['POST'])
def webhook():
    signature = request.headers.get('X-Hub-Signature-256')
    payload = request.data

    logger.info(f"Received webhook with signature: {signature}")
    logger.info(f"Payload: {payload.decode('utf-8')}")

    if not verify_webhook_signature(payload, signature):
        logger.warning("Webhook signature verification failed")
        return jsonify({"error": "Request signatures didn't match!"}), 403

    logger.info("Webhook signature verified successfully")

    event = request.headers.get('X-GitHub-Event')
    data = request.json

    logger.info(f"GitHub event: {event}")
    logger.info(f"Action: {data.get('action')}")

    if event == 'issues' and data['action'] == 'opened':
        issue = data['issue']
        repo = data['repository']
        owner = repo['owner']['login']
        repo_name = repo['name']

        result, status_code = create_pull_request_for_issue(owner, repo_name, issue)
        return jsonify(result), status_code
    elif event == 'pull_request_review_comment' and data['action'] == 'created':
        comment = data['comment']
        pull_request = data['pull_request']
        repo = data['repository']
        owner = repo['owner']['login']
        repo_name = repo['name']

        result, status_code = handle_pr_review_comment(owner, repo_name, pull_request, comment)
        return jsonify(result), status_code
    else:
        logger.info("Event is not handled, ignoring")
        return jsonify({"message": "Received"}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)

