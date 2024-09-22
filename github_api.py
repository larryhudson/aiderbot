import os
import requests
import jwt
import time
import logging

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

def create_branch(token, owner, repo, branch_name, sha):
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

def create_pull_request(token, owner, repo, title, body, head, base):
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

def create_issue_comment(token, owner, repo, issue_number, body):
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

def create_issue_reaction(token, owner, repo, issue_number, reaction):
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/reactions"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }

    data = {
        "content": reaction
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        reaction_id = response.json()['id']
        return reaction_id
    elif response.status_code == 200:
        reaction_id = response.json()['id']
        return reaction_id
    elif response.status_code == 422:
        logger.error(f"Failed to create issue reaction: {response.text}")
        return response.json()

def delete_issue_reaction(token, owner, repo, issue_number, reaction_id):
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/reactions/{reaction_id}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }

    response = requests.delete(url, headers=headers)
    if response.status_code == 204:
        return True
    else:
        logger.error(f"Failed to delete issue reaction: {response.text}")
        return False

def create_pr_review_comment_reaction(token, owner, repo, comment_id, reaction):
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/comments/{comment_id}/reactions"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "content": reaction
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        return response.json()
    else:
        logger.error(f"Failed to create PR review comment reaction: {response.text}")
        return None

def delete_pr_review_comment_reaction(token, owner, repo, comment_id, reaction_id):
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/comments/{comment_id}/reactions/{reaction_id}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }

    response = requests.delete(url, headers=headers)
    if response.status_code == 204:
        return True
    else:
        logger.error(f"Failed to delete PR review comment reaction: {response.text}")
        return False

def get_issue(token, owner, repo, issue_number):
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

def get_pr_diff(token, owner, repo, pr_number):
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

def get_pr_changed_files(token, owner, repo, pr_number):
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

def create_pr_comment(token, owner, repo, pr_number, body):
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

def reply_to_pr_review_comment(token, owner, repo, pr_number, pr_review_comment_id, body):
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments"

    headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
    }

    data = {
        "body": body,
        "in_reply_to": pr_review_comment_id
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        return response.json()
    else:
        logger.error(f"Failed to reply to PR review comment: {response.text}")
        return None
