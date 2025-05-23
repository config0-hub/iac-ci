### How to Generate a GitHub Token

1. **Log into GitHub:**
   - Open your web browser and go to [GitHub](https://github.com).
   - Log in with your GitHub credentials.

2. **Access Settings:**
   - Click on your profile picture in the upper right corner of the page.
   - From the dropdown menu, select **Settings**.

3. **Navigate to Developer Settings:**
   - In the left sidebar, scroll down and click on **Developer settings**.

4. **Personal Access Tokens:**
   - In the Developer settings menu, click on **Personal access tokens**.
   - If you see an option for **Tokens (classic)**, click on that.

5. **Generate New Token:**
   - Click the **Generate new token** button.
   - You may be prompted to re-enter your password for security.

6. **Configure Token Settings:**
   - **Note:** Provide a descriptive name for your token in the **Note** field.
   - **Expiration:** Choose an expiration time for your token (select an appropriate duration based on your needs).
   - **Select Scopes:** Check the following scopes based on your requirements:
     - **Required:**
       - `repo`: Grants full control of private repositories.
       - `gist`: Allows you to create and manage gists.
       - `write:discussion`: Allows writing to discussions.
     - **Optional:**
       - `write:deploy_keys`: Allows adding and removing SSH deploy keys.
       - `admin:repo_hook`: To manage webhook configurations.

7. **Generate the Token:**
   - After selecting the necessary scopes, scroll down and click on the **Generate token** button.

8. **Copy the API Token:**
   - After generating the token, copy and store in safe place.
