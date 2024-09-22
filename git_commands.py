import subprocess
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

def clone_repository(token, temp_dir, owner, repo, branch='main'):

    clone_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"

    # clone the repo into the temp_dir
    subprocess.run(['git', 'clone', clone_url, temp_dir], check=True)
    subprocess.run(['git', 'checkout', branch], cwd=temp_dir, check=True)

    return temp_dir

def checkout_new_branch(repo_dir, branch_name):
    try:
        subprocess.run(['git', 'checkout', '-b', branch_name], cwd=repo_dir, check=True)
        return True
    except:
        logger.error(f"Failed to checkout new branch: {branch_name}")
        return False

def push_changes_to_repository(temp_dir, branch):
    try:
        # First, fetch the latest changes from the remote
        subprocess.run(['git', 'fetch', 'origin'], cwd=temp_dir, check=True)
        
        # Check if the branch exists on the remote
        remote_branch_exists = subprocess.run(['git', 'ls-remote', '--exit-code', '--heads', 'origin', branch], 
                                              cwd=temp_dir, capture_output=True).returncode == 0

        push_command_args = ['git', 'push']
        if not remote_branch_exists:
            push_command_args += ['--set-upstream', 'origin', branch]
        else:
            push_command_args += ['origin', branch]

        subprocess.run(push_command_args, cwd=temp_dir, check=True)
        
        logger.info(f"Pushed changes to branch {branch}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to push changes to branch {branch}: {e}")
        logger.error(f"Command output: {e.output.decode() if e.output else 'No output'}")
        return False
