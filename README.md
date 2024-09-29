# Aider GitHub App

This GitHub App uses [Aider](https://aider.chat/) and [Claude 3.5 Sonnet](https://www.anthropic.com/news/claude-3-5-sonnet) to automatically create pull requests to resolve issues and respond to pull request review comments.

## How it works

This GitHub App automates the process of addressing issues and responding to pull request review comments. Here's an overview of how it works:

1. It uses a webhook to listen for GitHub repository events:
   - When a new issue is created
   - When a new pull request review comment is added
   - The app 'reacts' to the new issue / pull request review comment with the 👀 reaction to show that it is working.

2. It clones the repository to a temporary directory:
   - When an event is triggered, the app clones the repository to a temporary directory.
   - It uses Aider to run an LLM (Language Model) prompt that analyzes the issue or review comment and makes the necessary changes to the code.

3. Using Aider, it attempts to resolve the issue by making code changes.
   - It uses Aider's 'repo map' feature to choose which files it needs to edit.
   - Aider automatically creates a commit for each change it makes.

3. It pushes its changes to a new branch:
   - After making changes, the app creates a new branch in the repository.
   - It then pushes the new branch to GitHub.
   - Then it creates an issue comment that describes the pull request.

This automated workflow helps streamline the process of addressing issues and incorporating feedback, saving time for developers and maintainers.

To trigger the bot's action, you need to mention "@aiderbot" in the issue title or body, or in the pull request review comment. This ensures that the bot only responds when explicitly called upon.

## Celery Task Queue

The application uses Celery, a distributed task queue, to manage and execute the code analysis and modification tasks asynchronously. Here's how it works:

1. **Task Creation**: When a new issue is created or a pull request review comment is added, the app creates a Celery task.

2. **Task Queue**: The task is added to a Redis-backed queue, which allows for efficient task management and distribution.

3. **Worker Processing**: Celery workers, running in separate Docker containers, pick up tasks from the queue and execute them. This includes cloning the repository, running the Aider analysis, and making code changes.

4. **Asynchronous Execution**: By using Celery, the app can handle multiple requests simultaneously without blocking. This improves performance and allows the app to scale more easily.

5. **Task Status and Results**: The app can track the status of tasks and retrieve results asynchronously, enabling it to provide updates on the progress of issue resolution or comment responses.

This architecture ensures that the main application remains responsive while potentially time-consuming tasks are handled in the background.

This is an experiment and is still in early development, so expect bugs!

## Prerequisites

Before setting up the GitHub App, ensure you have the following:

- GitHub account
- Docker - e.g. [Docker Desktop](https://www.docker.com/products/docker-desktop/), [OrbStack for macOS](https://orbstack.dev/)
- Node.js and NPM - for running the Smee webhook server in local development
- Anthropic API token for Claude 3.5 model
- macOS Sonoma 14.3.1 or later (Note: This has been tested on macOS, but should work on other operating systems)

## Setup instructions

Follow these steps to set up and run the GitHub App, and get the webhook server running on your local machine:

1. **Clone the repository and set up the environment:**
   ```
   git clone <repository-url>
   cd <repository-directory>
   ```
2. **Set up a webhook URL with [Smee.io](https://smee.io/):**
   - Visit [Smee.io](https://smee.io/) and click "Start a new channel"
   - Keep this page open, you'll need the webhook URL in the next step

3. **[Set up a new GitHub App](https://docs.github.com/en/apps/creating-github-apps):**
   - Go to your GitHub account settings > Developer settings > GitHub Apps > New GitHub App
   - Fill in the required fields
   - Under 'Webhook', set the webhook URL to the one you created with Smee
   - [Generate a random string](https://www.random.org/strings/?num=10&len=32&digits=on&upperalpha=on&loweralpha=on&unique=on&format=html&rnd=new) and set it as the 'Webhook secret'
   - Under 'Repository permissions', set 'Issues', 'Pull requests' and 'Contents' to 'Read & write'
   - Under 'Subscribe to events', check 'Issues' and 'Pull request review comment'
   - Create the app
   - Under 'Private keys', generate a new private key and download it
   - Store the `.pem` file in the project directory

4. **Set up the environment variables:**
   - Duplicate `.env.sample` to `.env`
   - Replace the placeholder values in `.env`:
     - `GITHUB_WEBHOOK_SECRET`: the 'Webhook secret' string you generated
     - `GITHUB_APP_ID`: App ID at the top of the app settings
     - `GITHUB_PRIVATE_KEY_PATH`: relative path to .pem file (e.g., 'private-key.pem')
     - `GITHUB_APP_USER_NAME`: the 'name' of your GitHub app, followed by '[bot]'
     - `GIT_COMMIT_AUTHOR_NAME` and `GIT_COMMIT_AUTHOR_EMAIL`: your details which will be used in Aider's commits. You can find your public-facing GitHub email address in the [GitHub settings](https://github.com/settings/emails).

5. **Install the App:**
   - In the left sidebar of the app settings, click 'Install App'
   - Choose the repositories you want to enable it for

6. **Run the application:**
   - Build the Docker containers and run them:
     ```
     docker compose up -d
     ```
   - In a fourth terminal, start Smee to forward webhook requests:
     ```
     npx smee -u <your-smee-webhook-url> -t http://localhost:5000/webhook
     ```

7. **Test the App:**
   - Create a new issue in a repository where the app is installed
   - The app should react to the issue with the 'eyes' reaction, then create a PR to resolve the issue
   - Check the Flask dev server logs and Celery worker logs if you encounter any issues

## Troubleshooting

If you run into any problems, check the following:

- Ensure all environment variables in `.env` are correctly set
- Verify that the webhook URL in the GitHub App settings matches your Smee URL
- Check that the Smee client is running and forwarding requests
- Review the Flask dev server logs for any error messages

### Testing and Debugging Tips

- **Smee.io Redeliver Feature**: Within the Smee.io interface, you can use the 'Redeliver' button to resend a payload. This is particularly useful for testing after you've made changes or fixed a bug. Instead of manually creating new issues or PR review comments repeatedly, you can simply click 'Redeliver' to test your latest changes with the same payload.

For more detailed information, refer to the [GitHub Apps documentation](https://docs.github.com/en/developers/apps).
