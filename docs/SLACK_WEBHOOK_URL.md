# How to Create a Slack App and Get a Webhook URL

## Step 1: Create a Slack App

1. **Visit the Slack API Website:**
   - Go to the [Slack API website](https://api.slack.com/apps).

2. **Sign In to Your Workspace:**
   - Click on **Your Apps** and sign in to your Slack workspace if prompted.

3. **Create a New App:**
   - Click on the **Create New App** button.
   - Choose **From scratch**.

4. **Configure Your App:**
   - Enter a name for your app (e.g., "IAC-CI").
   - Select the workspace where you want to install the app.
   - Click **Create App**.

## Step 2: Set Up Incoming Webhooks

1. **Navigate to Incoming Webhooks:**
   - In your app settings, scroll down and click on **Incoming Webhooks** in the left sidebar.

2. **Activate Incoming Webhooks:**
   - Toggle the switch to enable **Activate Incoming Webhooks**.

3. **Add a New Webhook:**
   - Scroll down to the **Webhook URLs for Your Workspace** section.
   - Click on **Add New Webhook to Workspace**.

4. **Choose a Channel:**
   - Select the channel where you want the messages to be sent.
   - Click **Allow** to grant permissions.

5. **Copy the Webhook URL:**
   - After the webhook is created, you will see a new Webhook URL.
   - **Copy this URL** and store in a safe place.
