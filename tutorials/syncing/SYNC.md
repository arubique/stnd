This tutorial demonstrates how to synchronize the results table with a [Google Sheet](https://workspace.google.com/products/sheets/) and optionally upload the default config, stdout, and stderr logs to [Google Drive](https://drive.google.com/drive/my-drive).

## Preliminaries

### Be aware of the quick start guide

Before starting this tutorial, make sure you:

- Understand the gist of [Quick Start Guide](../quick_start_guide/QUICK_START_GUIDE.md).
- Have an [Anaconda](https://www.anaconda.com/) environment with the `stnd` package installed as described [here](../../README.md#installation).

### Prepare service account for Google Sheets and Docs

To write to remote Google Sheets or Drive, you need to create a service account that will handle the writes and have the necessary authorization. For that, please perform these steps:

1. Go to [Google Cloud Console](https://console.cloud.google.com/projectselector2/apis/dashboard)
2. Create a new project
   <details>
   <summary>Screenshot for "Create Project"</summary>
   <img src="./step_screenshots/create_project.png" alt="Create project">
   </details>
3. [Enable API access](https://docs.gspread.org/en/latest/oauth2.html#enable-api-access) for the following APIs:
- Google Sheets API
- Google Drive API (repeat the same steps as for Google Sheets, but for Google Drive)

    <details>
    <summary>Screenshot for "Enabling APIs"</summary>
    <img src="./step_screenshots/enable_api_services.png" alt="Enable API">
    </details>
    <details>
    <summary>Screenshot for "Enabling Google Sheet API"</summary>
    <img src="./step_screenshots/search_for_service.png" alt="Search for API">
    <img src="./step_screenshots/enable_api.png" alt="Enable API">
    </details>

4. Navigate to the **Credentials** section

    <details>
    <summary>Screenshot for "Credentials section"</summary>
    <img src="./step_screenshots/create_credentials.png" alt="Create Credentials">
    </details>

5. Click **"Create credentials"** → **Service account**

    <details>
    <summary>Screenshot for "Create service account"</summary>
    <img src="./step_screenshots/create_new_service_account.png" alt="Create Service Account">
    </details>

6. Select newly created Service Account in “Service Accounts” section of credentials page.

    <details>
    <summary>Screenshot for "Selecting new service account"</summary>
    <img src="./step_screenshots/push_on_account.png" alt="Selecting new service account">
    </details>

7. Remember its name e.g. myname@my-project-22062025-guide.iam.gserviceaccount.com in the example screenshot above.
8. Select newly created Service → go to tab Keys of the service page → Add key → Download key as JSON

    <details>
    <summary>Screenshots for "Creating credentials json"</summary>
    <img src="./step_screenshots/keys.png" alt="Keys">
    <img src="./step_screenshots/create_new_account.png" alt="Create new account">
    <img src="./step_screenshots/create_key.png" alt="Create json">
    </details>

9. Put the downloaded json with credentials inside `~/.config/gauth/service_key.json`

## Moving results table to Google Sheets

Now we are ready to synchronize results table with remote Google Sheets. For demonstration purposes we created a copy of [results.csv](../quick_start_guide/results.csv) in Google Sheets [by this link](https://docs.google.com/spreadsheets/d/1vfwGoh_5Nb0t0-Ohcj42jhOakgbyB6w4mlnt3lbskAc/edit?gid=0#gid=0). Please make a copy of it and share access to it with the service account created in step 7 in the [previous section](#prepare-service-account-for-google-sheets-and-docs).

<details>
<summary>Screenshot for "Sharing google sheet with service account"</summary>
<img src="./step_screenshots/share_gsheet.png" alt="Share google sheet">
</details>

Create a string in the format: `<link to google sheet>::<name of the worksheet>`

For example: `https://docs.google.com/spreadsheets/d/1vfwGoh_5Nb0t0-Ohcj42jhOakgbyB6w4mlnt3lbskAc/edit?gid=0#gid=0::Results_csv`. If the worksheet name contains spaces, wrap the entire string in quotes before using it in the terminal.

Use this string instead of the CSV path in the [command from quick start guide](../quick_start_guide/QUICK_START_GUIDE.md#run-experiment):

```
export ENV=<your env> && export PROJECT_ROOT_PROVIDED_FOR_STUNED=<repo with experiments> && conda activate $ENV && python -m stnd.run_from_csv.__main__ --csv_path <link to google sheet>::<name of the worksheet> --run_locally --conda_env $ENV
```
