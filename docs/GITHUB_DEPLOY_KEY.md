1. **Generate the SSH Key:**
   - Run the following command

     ```bash
     cd /var/tmp
     mkdir -p github/ssh_keys
     ssh-keygen -t rsa -b 2048 -C "CHANGEME_EMAIL" -f github/ssh_keys/iac-ci
     ```

2. **Navigate to Your Repository:**
   - Go to your GitHub repository e.g.**iac-ci**.

2. **Access Repository Settings:**
   - Click on the **Settings** tab in the repository.

3. **Manage Deploy Keys:**
   - Scroll down to **Deploy keys** in the left sidebar.
   - Click **Add deploy key**.
   - Provide a title for the key (e.g., "iac-ci system").
   - Open your public key file (e.g., `/var/tmp/github/ssh_keys/iac-ci.pub`) and copy its contents. Paste it into the **Key** field.

4. **Save the Deploy Key:**
   - Check the **Allow write access** box - need to push to the repository.
   - Click the **Add key** button to save.
