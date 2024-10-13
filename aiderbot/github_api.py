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
GITHUB_PRIVATE_KEY_CONTENTS = os.getenv('GITHUB_PRIVATE_KEY_CONTENTS')

def get_github_token_for_installation(installation_id):
    if not GITHUB_APP_ID:
        raise ValueError("GITHUB_APP_ID environment variable not set")
    if not GITHUB_PRIVATE_KEY_CONTENTS:
        raise ValueError("GITHUB_PRIVATE_KEY_CONTENTS environment variable not set")

    try:

        jwt_payload = {
            'iat': int(time.time()),
            'exp': int(time.time()) + 600,  # JWT expiration time (10 minutes maximum)
            'iss': GITHUB_APP_ID
        }

        # Create JWT
        jwt_token = jwt.encode(jwt_payload, GITHUB_PRIVATE_KEY_CONTENTS, algorithm='RS256')

        # Get an installation access token
        token_response = requests.post(
            f'https://api.github.com/app/installations/{installation_id}/access_tokens',
            headers={
                'Authorization': f'Bearer {jwt_token}',
                'Accept': 'application/vnd.github.v3+json'
            },
        )

        token_response.raise_for_status()
        return token_response.json()['token']
    except ValueError as e:
        logger.error(f"Private key contents error: {str(e)}")
        logger.info("The application will continue to run, but GitHub API calls will fail until the private key is provided.")
    except jwt.PyJWTError as e:
        logger.error(f"JWT encoding failed: {str(e)}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get GitHub token: {str(e)}")
    except KeyError:
        logger.error("Unexpected response format from GitHub API")
    except Exception as e:
        logger.error(f"Unexpected error in get_github_token: {str(e)}")

    return None

def _get_headers_with_token(token, accept="application/vnd.github.v3+json"):
    return {
        "Authorization": f"token {token}",
        "Accept": accept
    }


def create_branch(token, owner, repo, branch_name, sha):
    response = requests.post(
        f"https://api.github.com/repos/{owner}/{repo}/git/refs",
        headers=_get_headers_with_token(token),
        json={
            "ref": f"refs/heads/{branch_name}",
            "sha": sha
        }
    )
    if response.status_code == 201:
        return response.json()
    else:
        logger.error(f"Failed to create branch: {response.text}")
        return None

def create_pull_request(token, owner, repo, title, body, head, base):
    response = requests.post(
        f"https://api.github.com/repos/{owner}/{repo}/pulls",
        headers=_get_headers_with_token(token),
        json={
            "title": title,
            "body": body,
            "head": head,
            "base": base
        }
    )
    if response.status_code == 201:
        return response.json()
    else:
        logger.error(f"Failed to create pull request: {response.text}")
        return None

def create_issue_comment(token, owner, repo, issue_number, body):
    response = requests.post(
        f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments",
        headers=_get_headers_with_token(token),
        json={
            "body": body
        }
    )
    if response.status_code == 201:
        return response.json()
    else:
        logger.error(f"Failed to create issue comment: {response.text}")
        return None

def create_issue_reaction(token, owner, repo, issue_number, reaction):

    response = requests.post(
        f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/reactions",
        headers=_get_headers_with_token(token),
        json={
        "content": reaction
        }
    )

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

    response = requests.delete(
        f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/reactions/{reaction_id}",
        headers=_get_headers_with_token(token)
    )
    if response.status_code == 204:
        return True
    else:
        logger.error(f"Failed to delete issue reaction: {response.text}")
        return False

def create_pr_review_comment_reaction(token, owner, repo, pr_review_comment_id, reaction):
    response = requests.post(
        f"https://api.github.com/repos/{owner}/{repo}/pulls/comments/{pr_review_comment_id}/reactions",
        headers=_get_headers_with_token(token),
        json={
        "content": reaction
        }
    )

    if response.status_code == 201:
        return response.json()
    else:
        logger.error(f"Failed to create PR review comment reaction: {response.text}")
        return None

def delete_pr_review_comment_reaction(token, owner, repo, pr_review_comment_id, reaction_id):

    response = requests.delete(
        f"https://api.github.com/repos/{owner}/{repo}/pulls/comments/{pr_review_comment_id}/reactions/{reaction_id}",
        headers=_get_headers_with_token(token)
    )
    if response.status_code == 204:
        return True
    else:
        logger.error(f"Failed to delete PR review comment reaction: {response.text}")
        return False


def get_pull_requests_for_issue(token, owner, repo, issue_number):
    response = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/pulls",
        headers=_get_headers_with_token(token),
        params={
            "state": "open",
            "sort": "created",
            "direction": "desc"
        }
    )
    if response.status_code == 200:
        # TODO: is there a better way to look up pull requests linked to an issue? use search api?
        prs = response.json()
        return [pr for pr in prs if f"#{issue_number}" in pr['title']]
    else:
        logger.error(f"Failed to get pull requests: {response.text}")
        return []

def get_issue(token, owner, repo, issue_number):
    response = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}",
        headers=_get_headers_with_token(token)
    )
    if response.status_code == 200:
        return response.json()
    else:
        logger.error(f"Failed to get issue: {response.text}")
        return None

def get_pr_diff(token, owner, repo, pr_number):
    response = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
        headers=_get_headers_with_token(
            token,
            accept="application/vnd.github.v3.diff"
        )
    )
    if response.status_code == 200:
        return response.text
    else:
        logger.error(f"Failed to get PR diff: {response.text}")
        return None

def get_pr_changed_files(token, owner, repo, pr_number):
    response = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files",
        headers=_get_headers_with_token(token),
    )
    if response.status_code == 200:
        return [file['filename'] for file in response.json()]
    else:
        logger.error(f"Failed to get PR changed files: {response.text}")
        return []

def create_pr_comment(token, owner, repo, pr_number, body):
    response = requests.post(
        f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments",
        headers=_get_headers_with_token(token),
        json={
            "body": body
        }
    )
    if response.status_code == 201:
        return response.json()
    else:
        logger.error(f"Failed to create PR comment: {response.text}")
        return None

def reply_to_pr_review_comment(token, owner, repo, pr_number, pr_review_comment_id, body):
    response = requests.post(
        f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments",
        headers=_get_headers_with_token(token),
        json={
            "body": body,
            "in_reply_to": pr_review_comment_id
        }
    )

    if response.status_code == 201:
        return response.json()
    else:
        logger.error(f"Failed to reply to PR review comment: {response.text}")
        return None

def get_default_branch(token, owner, repo):
    response = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers=_get_headers_with_token(token)
    )

    if response.status_code == 200:
        return response.json()['default_branch']
    else:
        logger.error(f"Failed to get default branch: {response.text}")
        return None
