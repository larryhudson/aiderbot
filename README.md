# GitHub App for Issue Resolution

This GitHub App automatically creates pull requests to resolve issues and responds to pull request review comments.

## Setup Instructions

1. **Clone the repository and set up the environment:**
   ```
   git clone <repository-url>
   cd <repository-directory>
   python -m venv venv
   source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
   pip install -r requirements.txt
   ```

2. **Set up a webhook URL with [Smee.io](https://smee.io/):**
   - Visit [Smee.io](https://smee.io/) and click "Start a new channel"
   - Keep this page open, you'll need the URL in the next step

3. **[Set up a new GitHub App](https://docs.github.com/en/apps/creating-github-apps):**
   - Go to your GitHub account settings > Developer settings > GitHub Apps > New GitHub App
   - Under 'Webhook', set the webhook URL to the one you created with Smee
   - [Generate a random string](https://www.random.org/strings/?num=10&len=32&digits=on&upperalpha=on&loweralpha=on&unique=on&format=html&rnd=new) and set it as the 'Webhook secret'
   - Under 'Private keys', create a new private key and download it
   - Store the `.pem` file in the project directory

4. **Set up the environment variables:**
   - Duplicate `.env.sample` to `.env`
   - Replace the placeholder values in `.env`:
     - `GITHUB_WEBHOOK_SECRET`: the 'Webhook secret' string you generated
     - `GITHUB_APP_ID`: App ID at the top of the app settings
     - `GITHUB_PRIVATE_KEY_PATH`: relative path to .pem file (e.g., 'private-key.pem')
     - `GITHUB_APP_USER_NAME`: the 'name' of your GitHub app, followed by '[bot]'

5. **Install the App:**
   - In the left sidebar of the app settings, click 'Install App'
   - Choose the repositories you want to enable it for

6. **Run the application:**
   - Start the Flask dev server:
     ```
     python main.py
     ```
   - In a new terminal, start Smee to forward webhook requests:
     ```
     npx smee -u <your-smee-url> -t http://localhost:5000/webhook
     ```

7. **Test the app:**
   - Create a new issue in a repository where the app is installed
   - The app should react to the issue with the 'eyes' reaction, then create a PR to resolve the issue
   - Check the Flask dev server logs if you encounter any issues

## Troubleshooting

If you run into any problems, check the Flask dev server logs for error messages. Make sure all environment variables are set correctly in your `.env` file and that your GitHub App is properly configured.
