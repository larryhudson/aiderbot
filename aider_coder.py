from aider.repo import GitRepo
import os
import subprocess
from aider.coders import Coder
from aider.models import Model
from aider.io import InputOutput
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

def do_coding_request(prompt, files_list, root_folder_path):
    logger.info("Starting coding request")
    logger.info(f"Files List: {files_list}")
    
    model = Model("claude-3-5-sonnet-20240620")
    full_file_paths = [os.path.join(root_folder_path, file) for file in files_list]
    io = InputOutput(yes=True)
    git_repo = GitRepo(io, full_file_paths, root_folder_path, models=model.commit_message_models())
    coder = Coder.create(main_model=model, fnames=full_file_paths, io=io, repo=git_repo, stream=False, suggest_shell_commands=False)

    logger.info("Running coder with prompt")
    try:
        summary = coder.run(prompt)
        logger.info("Coding request completed")
    except Exception as e:
        logger.error(f"Error during coding request: {str(e)}")
        import traceback
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise  # Re-raise the exception to be caught by the outer try-except block

    # Get the last commit message
    commit_message = subprocess.check_output(['git', 'log', '-1', '--pretty=%B'], cwd=root_folder_path).decode('utf-8').strip()
    if not commit_message:
        commit_message = "Update files based on the latest request"
    logger.info(f"Commit message: {commit_message}")

    return {
        'commit_message': commit_message,
        'summary': summary
    }


def build_pr_review_prompt(issue, pr_diff, review_comment):
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